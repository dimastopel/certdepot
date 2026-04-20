// PEM Certificate Decoder - client-side X.509 parser
// Handles the common fields for display: subject, issuer, validity, SANs, public key, fingerprints.

(function () {
    "use strict";

    // ---------- PEM / Base64 ----------
    function pemToDer(pem) {
        const m = pem.match(/-----BEGIN ([A-Z ]+)-----([\s\S]*?)-----END \1-----/);
        if (!m) throw new Error("Could not find a PEM block. Expected -----BEGIN CERTIFICATE-----.");
        const label = m[1].trim();
        if (label !== "CERTIFICATE") {
            throw new Error(`Expected CERTIFICATE block, got ${label}.`);
        }
        const b64 = m[2].replace(/\s+/g, "");
        const bin = atob(b64);
        const der = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) der[i] = bin.charCodeAt(i);
        return der;
    }

    // ---------- ASN.1 DER parser (minimal) ----------
    // Returns a tree: { tag, class, constructed, length, contents (Uint8Array), children?, start, end }
    function parseAsn1(buf, offset = 0, endOffset = buf.length) {
        if (offset >= endOffset) throw new Error("ASN.1: unexpected end of data");
        const tagByte = buf[offset];
        const tagClass = (tagByte & 0xc0) >> 6;
        const constructed = (tagByte & 0x20) !== 0;
        let tagNumber = tagByte & 0x1f;
        let i = offset + 1;
        if (tagNumber === 0x1f) {
            tagNumber = 0;
            let b;
            do {
                if (i >= endOffset) throw new Error("ASN.1: truncated multi-byte tag");
                b = buf[i++];
                tagNumber = (tagNumber << 7) | (b & 0x7f);
            } while (b & 0x80);
        }
        if (i >= endOffset) throw new Error("ASN.1: missing length byte");
        const lenByte = buf[i++];
        let length = 0;
        if ((lenByte & 0x80) === 0) {
            length = lenByte;
        } else {
            const n = lenByte & 0x7f;
            if (n === 0) throw new Error("ASN.1: indefinite length not supported in DER");
            if (n > 4) throw new Error("ASN.1: length too large");
            for (let k = 0; k < n; k++) {
                if (i >= endOffset) throw new Error("ASN.1: truncated length");
                length = (length << 8) | buf[i++];
            }
        }
        const contentStart = i;
        const contentEnd = i + length;
        if (contentEnd > endOffset) throw new Error("ASN.1: content exceeds buffer");
        const node = {
            tag: tagNumber,
            class: tagClass, // 0=univ, 1=app, 2=context, 3=private
            constructed,
            length,
            contents: buf.subarray(contentStart, contentEnd),
            start: offset,
            end: contentEnd,
        };
        if (constructed) {
            node.children = [];
            let p = contentStart;
            while (p < contentEnd) {
                const child = parseAsn1(buf, p, contentEnd);
                node.children.push(child);
                p = child.end;
            }
        }
        return node;
    }

    // ---------- Helpers ----------
    function bytesToHex(bytes, sep = ":") {
        const h = Array.from(bytes, b => b.toString(16).padStart(2, "0").toUpperCase());
        return h.join(sep);
    }

    function bytesToBigIntHex(bytes) {
        // For INTEGER values (serial numbers). Handle optional leading 0x00 sign byte.
        let start = 0;
        if (bytes.length > 1 && bytes[0] === 0x00) start = 1;
        return bytesToHex(bytes.subarray(start), ":");
    }

    function readOid(bytes) {
        if (bytes.length === 0) return "";
        const parts = [];
        const first = bytes[0];
        parts.push(Math.floor(first / 40));
        parts.push(first % 40);
        let val = 0;
        for (let i = 1; i < bytes.length; i++) {
            val = (val << 7) | (bytes[i] & 0x7f);
            if ((bytes[i] & 0x80) === 0) {
                parts.push(val);
                val = 0;
            }
        }
        return parts.join(".");
    }

    function decodeUtf8(bytes) {
        return new TextDecoder("utf-8").decode(bytes);
    }

    // Read INTEGER as JS number (for small ints like version)
    function readIntegerSmall(bytes) {
        let v = 0;
        for (let i = 0; i < bytes.length; i++) v = (v << 8) | bytes[i];
        return v;
    }

    // Parse ASN.1 time (UTCTime YYMMDDHHMMSSZ or GeneralizedTime YYYYMMDDHHMMSSZ)
    function parseAsn1Time(node) {
        const s = decodeUtf8(node.contents);
        let y, mo, d, h, mi, se;
        if (node.tag === 23) {
            // UTCTime
            y = parseInt(s.substring(0, 2), 10);
            y = y >= 50 ? 1900 + y : 2000 + y;
            mo = parseInt(s.substring(2, 4), 10) - 1;
            d = parseInt(s.substring(4, 6), 10);
            h = parseInt(s.substring(6, 8), 10);
            mi = parseInt(s.substring(8, 10), 10);
            se = parseInt(s.substring(10, 12), 10) || 0;
        } else {
            // GeneralizedTime
            y = parseInt(s.substring(0, 4), 10);
            mo = parseInt(s.substring(4, 6), 10) - 1;
            d = parseInt(s.substring(6, 8), 10);
            h = parseInt(s.substring(8, 10), 10);
            mi = parseInt(s.substring(10, 12), 10);
            se = parseInt(s.substring(12, 14), 10) || 0;
        }
        return new Date(Date.UTC(y, mo, d, h, mi, se));
    }

    // ---------- OID lookup ----------
    const OID_NAMES = {
        "2.5.4.3": "CN",
        "2.5.4.4": "SN",
        "2.5.4.5": "serialNumber",
        "2.5.4.6": "C",
        "2.5.4.7": "L",
        "2.5.4.8": "ST",
        "2.5.4.9": "street",
        "2.5.4.10": "O",
        "2.5.4.11": "OU",
        "2.5.4.12": "title",
        "2.5.4.42": "GN",
        "1.2.840.113549.1.9.1": "E",
        // Signature algorithms
        "1.2.840.113549.1.1.1": "RSA",
        "1.2.840.113549.1.1.5": "SHA1-RSA",
        "1.2.840.113549.1.1.11": "SHA256-RSA",
        "1.2.840.113549.1.1.12": "SHA384-RSA",
        "1.2.840.113549.1.1.13": "SHA512-RSA",
        "1.2.840.10045.2.1": "EC-Public-Key",
        "1.2.840.10045.4.1": "ECDSA-SHA1",
        "1.2.840.10045.4.3.2": "ECDSA-SHA256",
        "1.2.840.10045.4.3.3": "ECDSA-SHA384",
        "1.2.840.10045.4.3.4": "ECDSA-SHA512",
        // Curves
        "1.2.840.10045.3.1.7": "P-256 (secp256r1)",
        "1.3.132.0.34": "P-384 (secp384r1)",
        "1.3.132.0.35": "P-521 (secp521r1)",
        // Extensions
        "2.5.29.14": "Subject Key Identifier",
        "2.5.29.15": "Key Usage",
        "2.5.29.17": "Subject Alternative Name",
        "2.5.29.19": "Basic Constraints",
        "2.5.29.31": "CRL Distribution Points",
        "2.5.29.32": "Certificate Policies",
        "2.5.29.35": "Authority Key Identifier",
        "2.5.29.37": "Extended Key Usage",
        "1.3.6.1.5.5.7.1.1": "Authority Info Access",
    };

    // ---------- X.509 parsing ----------
    function parseName(nameNode) {
        // Name ::= SEQUENCE OF RelativeDistinguishedName
        // Each RDN is a SET OF AttributeTypeAndValue (SEQUENCE {OID, ANY})
        const parts = [];
        for (const rdn of nameNode.children || []) {
            for (const atv of rdn.children || []) {
                if (!atv.children || atv.children.length < 2) continue;
                const oid = readOid(atv.children[0].contents);
                const val = decodeUtf8(atv.children[1].contents);
                const name = OID_NAMES[oid] || oid;
                parts.push(`${name}=${val}`);
            }
        }
        return parts.join(", ");
    }

    function parseSAN(extValue) {
        // extnValue is OCTET STRING wrapping a SEQUENCE OF GeneralName
        const inner = parseAsn1(extValue);
        const names = [];
        for (const gn of inner.children || []) {
            // context-specific tags: 0=otherName, 1=rfc822Name, 2=dNSName, 4=directoryName, 6=URI, 7=IP
            if (gn.class === 2) {
                if (gn.tag === 2) names.push("DNS:" + decodeUtf8(gn.contents));
                else if (gn.tag === 1) names.push("email:" + decodeUtf8(gn.contents));
                else if (gn.tag === 6) names.push("URI:" + decodeUtf8(gn.contents));
                else if (gn.tag === 7) {
                    const ip = gn.contents;
                    if (ip.length === 4) names.push("IP:" + Array.from(ip).join("."));
                    else if (ip.length === 16) {
                        const parts = [];
                        for (let i = 0; i < 16; i += 2) {
                            parts.push(((ip[i] << 8) | ip[i + 1]).toString(16));
                        }
                        names.push("IP:" + parts.join(":"));
                    }
                }
            }
        }
        return names;
    }

    function parseBasicConstraints(extValue) {
        const inner = parseAsn1(extValue);
        let isCA = false;
        let pathLen = null;
        for (const child of inner.children || []) {
            if (child.tag === 1) isCA = child.contents[0] !== 0;
            else if (child.tag === 2) pathLen = readIntegerSmall(child.contents);
        }
        return { isCA, pathLen };
    }

    function parseKeyUsage(extValue) {
        const inner = parseAsn1(extValue);
        // BIT STRING: first byte = unused bits
        const unused = inner.contents[0];
        const bits = inner.contents.subarray(1);
        const flags = [
            "Digital Signature", "Non-Repudiation", "Key Encipherment", "Data Encipherment",
            "Key Agreement", "Key Cert Sign", "CRL Sign", "Encipher Only", "Decipher Only"
        ];
        const result = [];
        for (let i = 0; i < flags.length; i++) {
            const byte = Math.floor(i / 8);
            const bit = 7 - (i % 8);
            if (byte < bits.length && (bits[byte] & (1 << bit))) {
                result.push(flags[i]);
            }
        }
        return result;
    }

    function parseExtendedKeyUsage(extValue) {
        const inner = parseAsn1(extValue);
        const EKU_NAMES = {
            "1.3.6.1.5.5.7.3.1": "Server Authentication",
            "1.3.6.1.5.5.7.3.2": "Client Authentication",
            "1.3.6.1.5.5.7.3.3": "Code Signing",
            "1.3.6.1.5.5.7.3.4": "Email Protection",
            "1.3.6.1.5.5.7.3.8": "Time Stamping",
            "1.3.6.1.5.5.7.3.9": "OCSP Signing",
        };
        return (inner.children || []).map(c => {
            const oid = readOid(c.contents);
            return EKU_NAMES[oid] || oid;
        });
    }

    function parsePublicKeyInfo(spkiNode) {
        // SubjectPublicKeyInfo ::= SEQUENCE {
        //   algorithm        AlgorithmIdentifier,
        //   subjectPublicKey BIT STRING
        // }
        const algId = spkiNode.children[0];
        const algOid = readOid(algId.children[0].contents);
        const algName = OID_NAMES[algOid] || algOid;
        const bitString = spkiNode.children[1];
        const keyBytes = bitString.contents.subarray(1); // skip unused-bits byte

        let details = { algorithm: algName, algorithmOid: algOid };

        if (algOid === "1.2.840.113549.1.1.1") {
            // RSA: parse RSAPublicKey { modulus INTEGER, publicExponent INTEGER }
            try {
                const rsaPub = parseAsn1(keyBytes);
                const modulus = rsaPub.children[0].contents;
                const mod = modulus[0] === 0x00 ? modulus.subarray(1) : modulus;
                details.keySize = mod.length * 8;
                details.exponent = "0x" + bytesToHex(rsaPub.children[1].contents, "");
            } catch (e) { /* ignore */ }
        } else if (algOid === "1.2.840.10045.2.1") {
            // EC
            if (algId.children.length > 1) {
                const curveOid = readOid(algId.children[1].contents);
                details.curve = OID_NAMES[curveOid] || curveOid;
            }
            // Uncompressed EC point has 0x04 prefix, so key size = (len-1)/2 * 8
            if (keyBytes.length > 1 && keyBytes[0] === 0x04) {
                details.keySize = ((keyBytes.length - 1) / 2) * 8;
            }
        }

        return details;
    }

    function parseCertificate(der) {
        const cert = parseAsn1(der);
        if (!cert.constructed || cert.tag !== 16) throw new Error("Expected SEQUENCE (Certificate)");
        const tbs = cert.children[0];
        const sigAlg = cert.children[1];
        const sigValue = cert.children[2];

        // TBSCertificate fields
        let idx = 0;
        let version = 1;
        const first = tbs.children[0];
        if (first.class === 2 && first.tag === 0) {
            // [0] EXPLICIT Version
            version = readIntegerSmall(first.children[0].contents) + 1;
            idx = 1;
        }
        const serial = tbs.children[idx++];
        const tbsSigAlg = tbs.children[idx++];
        const issuer = tbs.children[idx++];
        const validity = tbs.children[idx++];
        const subject = tbs.children[idx++];
        const spki = tbs.children[idx++];

        // Extensions are tagged [3] EXPLICIT Extensions (after optional issuerUniqueID [1], subjectUniqueID [2])
        const extensions = [];
        for (; idx < tbs.children.length; idx++) {
            const c = tbs.children[idx];
            if (c.class === 2 && c.tag === 3) {
                const extSeq = c.children[0];
                for (const ext of extSeq.children || []) {
                    const oid = readOid(ext.children[0].contents);
                    let critical = false;
                    let valNode;
                    if (ext.children.length === 3) {
                        critical = ext.children[1].contents[0] !== 0;
                        valNode = ext.children[2];
                    } else {
                        valNode = ext.children[1];
                    }
                    extensions.push({
                        oid,
                        name: OID_NAMES[oid] || oid,
                        critical,
                        value: valNode.contents,
                    });
                }
            }
        }

        return {
            version,
            serial: bytesToBigIntHex(serial.contents),
            issuer: parseName(issuer),
            subject: parseName(subject),
            notBefore: parseAsn1Time(validity.children[0]),
            notAfter: parseAsn1Time(validity.children[1]),
            signatureAlgorithm: (() => {
                const oid = readOid(sigAlg.children[0].contents);
                return { name: OID_NAMES[oid] || oid, oid };
            })(),
            publicKey: parsePublicKeyInfo(spki),
            extensions,
        };
    }

    // ---------- Fingerprints ----------
    async function digest(algo, bytes) {
        const buf = await crypto.subtle.digest(algo, bytes);
        return bytesToHex(new Uint8Array(buf), ":");
    }

    // ---------- Render ----------
    function field(label, value) {
        const wrap = document.createElement("div");
        wrap.className = "pem-field";
        const l = document.createElement("div");
        l.className = "pem-label";
        l.textContent = label;
        const v = document.createElement("div");
        v.className = "pem-value";
        if (value instanceof Node) v.appendChild(value);
        else v.textContent = value;
        wrap.appendChild(l);
        wrap.appendChild(v);
        return wrap;
    }

    function section(title) {
        const s = document.createElement("div");
        s.className = "pem-section";
        const h = document.createElement("h3");
        h.textContent = title;
        s.appendChild(h);
        return s;
    }

    function renderCert(cert, fingerprintSha1, fingerprintSha256) {
        const root = document.createDocumentFragment();

        const top = section("Summary");
        top.appendChild(field("Version", `v${cert.version}`));
        top.appendChild(field("Serial Number", cert.serial));
        top.appendChild(field("Signature Alg.", cert.signatureAlgorithm.name));
        root.appendChild(top);

        const sub = section("Subject");
        sub.appendChild(field("Distinguished Name", cert.subject || "(empty)"));
        root.appendChild(sub);

        const iss = section("Issuer");
        iss.appendChild(field("Distinguished Name", cert.issuer || "(empty)"));
        root.appendChild(iss);

        const val = section("Validity");
        val.appendChild(field("Not Before", cert.notBefore.toUTCString()));
        val.appendChild(field("Not After", cert.notAfter.toUTCString()));
        const now = new Date();
        let status;
        if (now < cert.notBefore) status = "Not yet valid";
        else if (now > cert.notAfter) status = "EXPIRED";
        else {
            const daysLeft = Math.floor((cert.notAfter - now) / 86400000);
            status = `Valid (${daysLeft} days remaining)`;
        }
        val.appendChild(field("Status", status));
        root.appendChild(val);

        const pk = section("Public Key");
        pk.appendChild(field("Algorithm", cert.publicKey.algorithm));
        if (cert.publicKey.keySize) pk.appendChild(field("Size", `${cert.publicKey.keySize} bits`));
        if (cert.publicKey.curve) pk.appendChild(field("Curve", cert.publicKey.curve));
        if (cert.publicKey.exponent) pk.appendChild(field("Exponent", cert.publicKey.exponent));
        root.appendChild(pk);

        if (cert.extensions.length > 0) {
            const ext = section("Extensions");
            for (const e of cert.extensions) {
                let valueText;
                if (e.oid === "2.5.29.17") {
                    valueText = parseSAN(e.value).join(", ") || "(empty)";
                } else if (e.oid === "2.5.29.19") {
                    const bc = parseBasicConstraints(e.value);
                    valueText = `CA: ${bc.isCA}` + (bc.pathLen !== null ? `, pathLen: ${bc.pathLen}` : "");
                } else if (e.oid === "2.5.29.15") {
                    valueText = parseKeyUsage(e.value).join(", ") || "(none)";
                } else if (e.oid === "2.5.29.37") {
                    valueText = parseExtendedKeyUsage(e.value).join(", ") || "(none)";
                } else {
                    valueText = `(binary, ${e.value.length} bytes)`;
                }
                const label = e.name + (e.critical ? " (critical)" : "");
                ext.appendChild(field(label, valueText));
            }
            root.appendChild(ext);
        }

        const fp = section("Fingerprints");
        fp.appendChild(field("SHA-1", fingerprintSha1));
        fp.appendChild(field("SHA-256", fingerprintSha256));
        root.appendChild(fp);

        return root;
    }

    // ---------- UI wiring ----------
    const input = document.getElementById("pemInput");
    const decodeBtn = document.getElementById("decodeBtn");
    const clearBtn = document.getElementById("clearBtn");
    const errorEl = document.getElementById("pemError");
    const resultsEl = document.getElementById("results");
    const resultContent = document.getElementById("resultContent");

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.classList.remove("hidden");
        resultsEl.classList.add("hidden");
    }

    function clearError() {
        errorEl.classList.add("hidden");
        errorEl.textContent = "";
    }

    decodeBtn.addEventListener("click", async function () {
        clearError();
        const pem = input.value.trim();
        if (!pem) {
            showError("Please paste a PEM certificate.");
            return;
        }
        try {
            const der = pemToDer(pem);
            const cert = parseCertificate(der);
            const sha1 = await digest("SHA-1", der);
            const sha256 = await digest("SHA-256", der);
            resultContent.innerHTML = "";
            resultContent.appendChild(renderCert(cert, sha1, sha256));
            resultsEl.classList.remove("hidden");
        } catch (e) {
            showError("Failed to parse certificate: " + e.message);
        }
    });

    clearBtn.addEventListener("click", function () {
        input.value = "";
        clearError();
        resultsEl.classList.add("hidden");
    });
})();
