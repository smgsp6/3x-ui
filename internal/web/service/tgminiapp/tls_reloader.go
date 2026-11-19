package tgminiapp

// TLSCertificateReloader watches the panel's configured on-disk certificate
// pair and swaps it into future handshakes once BOTH files form a valid pair.
// Incomplete/non-matching ACME renewals never replace the last working pair.
// It does not issue certificates, start shell commands, or disclose paths.

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"os"
	"slices"
	"sync"
	"time"
)

const maxTLSPEMBytes = 2 << 20
const tlsRefreshInterval = 30 * time.Second

// LoadServerTLSKeyPair applies Vela's bounded certificate policy at startup.
// In original panel mode it preserves the upstream TLS loader's behavior.
func LoadServerTLSKeyPair(certPath, keyPath string) (tls.Certificate, error) {
	if !Enabled() {
		return tls.LoadX509KeyPair(certPath, keyPath)
	}
	pair, err := safeLoadTLSKeyPair(certPath, keyPath)
	if err != nil {
		return tls.Certificate{}, err
	}
	return *pair, nil
}

// TLSCertificateReloader keeps a pointer to an immutable certificate. Returning
// pointers to mutated tls.Certificate structs would race with TLS handshakes.
type TLSCertificateReloader struct {
	mu        sync.Mutex
	certPath  string
	keyPath   string
	current   *tls.Certificate
	nextCheck time.Time
}

func NewTLSCertificateReloader(certPath, keyPath string, initial tls.Certificate) *TLSCertificateReloader {
	// Both paths come from existing panel settings, not from an HTTP payload.
	return &TLSCertificateReloader{certPath: certPath, keyPath: keyPath, current: &initial, nextCheck: time.Now().Add(tlsRefreshInterval)}
}

// readTLSPEM allows ordinary ACME symlinks but bounds each read and checks
// the opened file still matches the regular file inspected before opening.
func readTLSPEM(path string) ([]byte, error) {
	before, err := os.Stat(path)
	if err != nil || !before.Mode().IsRegular() || before.Size() <= 0 || before.Size() > maxTLSPEMBytes {
		return nil, errors.New("TLS certificate material unavailable")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, errors.New("TLS certificate material unavailable")
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !os.SameFile(before, opened) || !opened.Mode().IsRegular() {
		return nil, errors.New("TLS certificate material changed during read")
	}
	data, err := io.ReadAll(io.LimitReader(file, maxTLSPEMBytes+1))
	if err != nil || len(data) == 0 || len(data) > maxTLSPEMBytes {
		return nil, errors.New("TLS certificate material invalid")
	}
	return data, nil
}

func safeLoadTLSKeyPair(certPath, keyPath string) (*tls.Certificate, error) {
	certPEM, err := readTLSPEM(certPath)
	if err != nil {
		return nil, err
	}
	keyPEM, err := readTLSPEM(keyPath)
	if err != nil {
		return nil, err
	}
	// A mismatched or half-written renewal must not replace the working pair.
	cert, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil || len(cert.Certificate) == 0 {
		return nil, errors.New("TLS certificate material invalid")
	}
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	now := time.Now()
	if err != nil || now.Before(leaf.NotBefore) || !now.Before(leaf.NotAfter) {
		return nil, errors.New("TLS certificate is not currently valid")
	}
	if !validSuppliedTLSChain(leaf, cert.Certificate[1:], now) {
		return nil, errors.New("TLS certificate chain is invalid")
	}
	cert.Leaf = leaf
	// The client will validate trust against its own CA roots.
	return &cert, nil
}

func validSuppliedTLSChain(child *x509.Certificate, issuers [][]byte, now time.Time) bool {
	for _, der := range issuers {
		issuer, err := x509.ParseCertificate(der)
		if err != nil || now.Before(issuer.NotBefore) || !now.Before(issuer.NotAfter) ||
			!bytes.Equal(child.RawIssuer, issuer.RawSubject) || child.CheckSignatureFrom(issuer) != nil {
			return false
		}
		child = issuer
	}
	return true
}

// Keeps all previously served DNS/IP SAN identities on automatic renewal.
// A deliberate hostname replacement requires operator review and restart.
func keepsCertificateIdentity(oldLeaf, candidate *x509.Certificate) bool {
	for _, name := range oldLeaf.DNSNames {
		if !slices.Contains(candidate.DNSNames, name) {
			return false
		}
	}
	for _, oldIP := range oldLeaf.IPAddresses {
		found := false
		for _, newIP := range candidate.IPAddresses {
			if oldIP.Equal(newIP) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	if len(oldLeaf.DNSNames) == 0 && len(oldLeaf.IPAddresses) == 0 &&
		oldLeaf.Subject.CommonName != candidate.Subject.CommonName {
		return false
	}
	return true
}

func losesKnownIssuers(current, candidate *tls.Certificate) bool {
	if len(candidate.Certificate) >= len(current.Certificate) {
		return false
	}
	if bytes.Equal(candidate.Certificate[0], current.Certificate[0]) {
		return true
	}
	tail := candidate.Leaf
	if len(candidate.Certificate) > 1 {
		var err error
		tail, err = x509.ParseCertificate(candidate.Certificate[len(candidate.Certificate)-1])
		if err != nil {
			return true
		}
	}
	// A truncated bundle may end at any intermediate, not only at the leaf.
	for _, der := range current.Certificate[1:] {
		issuer, err := x509.ParseCertificate(der)
		if err == nil && !bytes.Equal(tail.Raw, issuer.Raw) &&
			bytes.Equal(tail.RawIssuer, issuer.RawSubject) && tail.CheckSignatureFrom(issuer) == nil {
			return true
		}
	}
	return false
}

// currentAt is separated from TLS to permit deterministic offline rotation
// tests. It polls at most once per interval, not once per network request.
func (r *TLSCertificateReloader) currentAt(now time.Time) *tls.Certificate {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !now.Before(r.nextCheck) {
		r.nextCheck = now.Add(tlsRefreshInterval)
		if candidate, err := safeLoadTLSKeyPair(r.certPath, r.keyPath); err == nil {
			if !slices.EqualFunc(candidate.Certificate, r.current.Certificate, bytes.Equal) {
				// Prevent accidental replacement with an older, shorter-lived
				// certificate; a deliberate manual change can still restart.
				newLeaf := candidate.Leaf
				oldLeaf, oldErr := x509.ParseCertificate(r.current.Certificate[0])
				if oldErr == nil && !losesKnownIssuers(r.current, candidate) &&
					!newLeaf.NotAfter.Before(oldLeaf.NotAfter) && keepsCertificateIdentity(oldLeaf, newLeaf) {
					r.current = candidate
				}
			}
		}
	}
	return r.current
}

// GetCertificate implements tls.Config.GetCertificate. In Vela mode the
// config must set Certificates=nil, so SNI-less clients also use the reloader.
func (r *TLSCertificateReloader) GetCertificate(_ *tls.ClientHelloInfo) (*tls.Certificate, error) {
	return r.currentAt(time.Now()), nil
}
