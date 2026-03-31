document.addEventListener("DOMContentLoaded", function () {
    const step1 = document.getElementById("step1");
    const step2 = document.getElementById("step2");
    const commonNameInput = document.getElementById("commonName");
    const cnDisplay = document.getElementById("cnDisplay");
    const cnError = document.getElementById("cnError");
    const nextBtn = document.getElementById("nextBtn");
    const backBtn = document.getElementById("backBtn");
    const generateBtn = document.getElementById("generateBtn");
    const generateError = document.getElementById("generateError");
    const pfxPasswordGroup = document.getElementById("pfxPasswordGroup");
    const pfxPasswordInput = document.getElementById("pfxPassword");
    const pfxError = document.getElementById("pfxError");
    const counterDisplay = document.getElementById("counterDisplay");

    // Load certificate count
    fetch("/api/stats")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.certificatesGenerated > 0) {
                counterDisplay.textContent = data.certificatesGenerated.toLocaleString() + " certificates generated so far";
            }
        })
        .catch(function () {});

    // Step 1 -> Step 2
    nextBtn.addEventListener("click", function () {
        var cn = commonNameInput.value.trim();
        if (!cn) {
            cnError.classList.remove("hidden");
            commonNameInput.focus();
            return;
        }
        cnError.classList.add("hidden");
        cnDisplay.textContent = cn;
        step1.classList.add("hidden");
        step2.classList.remove("hidden");
    });

    // Allow Enter key on step 1
    commonNameInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            nextBtn.click();
        }
    });

    // Back to step 1
    backBtn.addEventListener("click", function () {
        step2.classList.add("hidden");
        step1.classList.remove("hidden");
        commonNameInput.focus();
    });

    // Toggle PFX password field
    document.querySelectorAll('input[name="outputFormat"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
            if (this.value === "pfx") {
                pfxPasswordGroup.classList.remove("hidden");
                pfxPasswordInput.focus();
            } else {
                pfxPasswordGroup.classList.add("hidden");
                pfxError.classList.add("hidden");
            }
        });
    });

    // Generate certificate
    generateBtn.addEventListener("click", function () {
        generateError.classList.add("hidden");
        pfxError.classList.add("hidden");

        var outputFormat = document.querySelector('input[name="outputFormat"]:checked').value;

        if (outputFormat === "pfx" && pfxPasswordInput.value.length < 4) {
            pfxError.classList.remove("hidden");
            pfxPasswordInput.focus();
            return;
        }

        var payload = {
            commonName: commonNameInput.value.trim(),
            keyType: document.getElementById("keyType").value,
            validityDays: parseInt(document.getElementById("validityDays").value, 10) || 365,
            outputFormat: outputFormat
        };

        // Add optional fields only if filled
        var optionals = {
            country: "country",
            state: "state",
            city: "city",
            organization: "organization",
            orgUnit: "orgUnit",
            email: "email"
        };
        for (var key in optionals) {
            var val = document.getElementById(optionals[key]).value.trim();
            if (val) payload[key] = val;
        }

        if (outputFormat === "pfx") {
            payload.pfxPassword = pfxPasswordInput.value;
        }

        // Disable button and show loading state
        generateBtn.disabled = true;
        generateBtn.textContent = "Generating...";
        generateBtn.classList.add("opacity-70");

        fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(function (response) {
            if (!response.ok) {
                return response.json().then(function (data) {
                    throw new Error(data.error || "Generation failed");
                });
            }
            var disposition = response.headers.get("Content-Disposition");
            var filename = "certificate." + outputFormat;
            if (disposition) {
                var match = disposition.match(/filename="?([^"]+)"?/);
                if (match) filename = match[1];
            }
            return response.blob().then(function (blob) {
                return { blob: blob, filename: filename };
            });
        })
        .then(function (result) {
            var url = URL.createObjectURL(result.blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = result.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            // Update counter display
            fetch("/api/stats")
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.certificatesGenerated > 0) {
                        counterDisplay.textContent = data.certificatesGenerated.toLocaleString() + " certificates generated so far";
                    }
                })
                .catch(function () {});
        })
        .catch(function (err) {
            generateError.textContent = err.message;
            generateError.classList.remove("hidden");
        })
        .finally(function () {
            generateBtn.disabled = false;
            generateBtn.textContent = "Generate Certificate";
            generateBtn.classList.remove("opacity-70");
        });
    });
});
