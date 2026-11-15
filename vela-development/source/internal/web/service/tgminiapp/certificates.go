package tgminiapp

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"os"
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
	// Reject unexpectedly large files (e.g. a wrong path pointing at a log)
	// rather than loading them into memory via os.ReadFile/LoadX509KeyPair.
	const maxPEMSize = 2 << 20
	for _, path := range []string{certPath, keyPath} {
		info, err := os.Stat(path)
		if err != nil || !info.Mode().IsRegular() || info.Size() > maxPEMSize {
			return result
		}
	}
	raw, err := os.ReadFile(certPath)
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
	// Confirm the configured private key corresponds to this public certificate.
	// tls.LoadX509KeyPair reads the key but never returns/serializes its contents.
	if _, err := tls.LoadX509KeyPair(certPath, keyPath); err != nil {
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
