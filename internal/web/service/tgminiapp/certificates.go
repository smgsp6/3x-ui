package tgminiapp

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"time"
)

// CertificateStatus contains public metadata only. Never return host filesystem
// paths or private-key bytes to the browser, even for an authenticated admin.
type CertificateStatus struct {
	Purpose       string     `json:"purpose"`
	DNSNames      []string   `json:"dnsNames"`
	Issuer        string     `json:"issuer,omitempty"`
	ValidFrom     *time.Time `json:"validFrom,omitempty"`
	ValidUntil    *time.Time `json:"validUntil,omitempty"`
	DaysRemaining int        `json:"daysRemaining"`
	Status        string     `json:"status"` // unconfigured, valid, expiring, expired, invalid
}

func InspectCertificate(purpose, certPath, keyPath string, now time.Time) CertificateStatus {
	result := CertificateStatus{Purpose: purpose, Status: "unconfigured", DNSNames: []string{}}
	if certPath == "" && keyPath == "" {
		return result
	}
	result.Status = "invalid"
	if certPath == "" || keyPath == "" {
		return result
	}
	// Only read paths already saved in panel settings. This function accepts
	// NO HTTP path input; the API handler never lets a client pick filenames.
	raw, err := readTLSPEM(certPath)
	if err != nil {
		return result
	}
	block, _ := pem.Decode(raw)
	if block == nil || block.Type != "CERTIFICATE" {
		return result
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return result
	}
	result.DNSNames = cert.DNSNames
	result.Issuer = cert.Issuer.CommonName
	result.ValidFrom, result.ValidUntil = &cert.NotBefore, &cert.NotAfter
	key, err := readTLSPEM(keyPath)
	if err != nil {
		return result
	}
	// Match the key to the same certificate bytes used for the status above.
	pair, err := tls.X509KeyPair(raw, key)
	if err != nil || !validSuppliedTLSChain(cert, pair.Certificate[1:], now) {
		return result
	}
	if now.Before(cert.NotBefore) {
		result.Status = "invalid"
	} else if !now.Before(cert.NotAfter) {
		result.Status = "expired"
	} else if cert.NotAfter.Sub(now) <= 30*24*time.Hour {
		result.Status = "expiring"
	} else {
		result.Status = "valid"
	}
	if now.Before(cert.NotAfter) {
		result.DaysRemaining = int(cert.NotAfter.Sub(now).Hours() / 24)
	}
	return result
}
