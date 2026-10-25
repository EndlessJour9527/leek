"""Seal private input snapshots for the requester; never publish plaintext inputs.

Only the public encryption key is in Git. Matching ephemeral private key remains
outside the repository. RSA-OAEP wraps a random AES-256-GCM key. No credentials.
"""
import argparse
import base64
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import zipfile

from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .data import encoded
AAD=b'leek/ML001/private-source-snapshot/v1'


def seal(root,public_key_path,output):
    root=Path(root).resolve();output=Path(output)
    if output.exists():raise ValueError('refuse existing encrypted output')
    pub_bytes=Path(public_key_path).read_bytes();pub=serialization.load_pem_public_key(pub_bytes)
    if not isinstance(pub,rsa.RSAPublicKey) or pub.key_size<3072:raise ValueError('RSA-3072+ public key required')
    memory=io.BytesIO();count=0
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_symlink():raise ValueError('refuse source symlink')
            if p.is_file():
                if p.stat().st_size>5_000_000:raise ValueError('oversized snapshot member')
                z.writestr(p.relative_to(root).as_posix(),p.read_bytes());count+=1
    if not count:raise ValueError('no source snapshot')
    plain=memory.getvalue();key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
    wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    b64=lambda x:base64.b64encode(x).decode('ascii')
    envelope=dict(version='ml001-private-envelope.v1',cipher='AES-256-GCM+RSA-OAEP-SHA256',
        public_key_sha256=sha256(pub_bytes).hexdigest(),aad=b64(AAD),nonce=b64(nonce),wrapped_key=b64(wrapped),
        ciphertext=b64(AESGCM(key).encrypt(nonce,plain,AAD)),plaintext_sha256=sha256(plain).hexdigest(),files=count)
    output.write_bytes(encoded(envelope))
    print(json.dumps({'encrypted_private_snapshot':True,'files':count,'ciphertext_sha256':sha256(output.read_bytes()).hexdigest()}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',required=True);p.add_argument('--public-key',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();seal(a.input_dir,a.public_key,a.output)


if __name__=='__main__':main()
