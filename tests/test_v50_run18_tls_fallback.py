"""Secure recovery on Ministry hostname with incomplete TLS certificate chain."""
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import official_sources_v50 as source

URL='https://inclusion.gob.es/documents/a.pdf/uuid?version=1.0'

class Run18TLSFallback(unittest.TestCase):
    def test_domain_fallback_is_official_https_only(self):
        self.assertEqual(source.official_tls_alternative(URL),URL.replace('://inclusion.gob.es','://www.inclusion.gob.es'))
        self.assertIsNone(source.official_tls_alternative('https://attacker.test/a.pdf'))
        self.assertIsNone(source.official_tls_alternative('http://inclusion.gob.es/a.pdf'))
        self.assertIsNone(source.official_tls_alternative('https://www.inclusion.gob.es/a.pdf'))

    def test_detects_specific_ssl_failure(self):
        self.assertTrue(source.is_certificate_verification_error(URLError(ssl.SSLCertVerificationError(1,'cert chain'))))
        self.assertFalse(source.is_certificate_verification_error(URLError('timeout')))

    def test_retries_with_tls_validation_enabled(self):
        visited=[]
        class FakeResponse:
            def __init__(self,url):
                self.url=url
                self.headers={'Content-Type':'application/pdf'}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,*a):return b'%PDF-synthetic-test-content'
        class Opener:
            def open(self,req,timeout):
                visited.append(req.full_url)
                if len(visited)==1:
                    raise URLError(ssl.SSLCertVerificationError(1,'certificate verify failed'))
                return FakeResponse(req.full_url)
        with patch.object(source,'build_opener',return_value=Opener()),patch.object(source,'extract_pdf_text',return_value='La modificacion se ajusta al articulo 191. '*30):
            rec=source.retrieve_one('migraciones','Guía de continuidad',URL)
        self.assertEqual(visited,[URL,source.official_tls_alternative(URL)])
        self.assertEqual(rec['retrieval_url'],visited[-1])
        self.assertEqual(rec['legal_status'],'PROCEDURAL_GUIDANCE_UNVERIFIED')

    def test_second_certificate_failure_is_not_ignored(self):
        visited=[]
        class Opener:
            def open(self,req,timeout):
                visited.append(req.full_url)
                raise URLError(ssl.SSLCertVerificationError(1,'certificate verify failed'))
        with patch.object(source,'build_opener',return_value=Opener()):
            with self.assertRaises(URLError):
                source.retrieve_one('migraciones','Guía',URL)
        self.assertEqual(len(visited),2)

    def test_non_tls_error_does_not_trigger_fallback(self):
        visited=[]
        class Opener:
            def open(self,req,timeout):
                visited.append(req.full_url)
                raise URLError('timeout')
        with patch.object(source,'build_opener',return_value=Opener()):
            with self.assertRaises(URLError):source.retrieve_one('migraciones','Guía',URL)
        self.assertEqual(visited,[URL])

if __name__=='__main__':unittest.main()
