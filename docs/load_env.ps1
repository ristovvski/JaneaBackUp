# Load the project .env into the current PowerShell session.
#
# Every past session set these by hand with $env:VAR = "..." inside one shell, which is why they
# vanished with that shell and the next chat found nothing on disk. Source this instead:
#
#     . "C:\Users\User\Desktop\Нова папка\load_env.ps1"
#
# Values are never echoed - it prints variable names and lengths only, so a paste into chat or a
# screenshot cannot leak a key.

$envPath = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envPath)) {
    Write-Output "MISSING: $envPath"
    return
}

$loaded = @()
foreach ($line in (Get-Content $envPath -Encoding UTF8)) {
    $t = $line.Trim()
    if ($t -eq "" -or $t.StartsWith("#")) { continue }
    $i = $t.IndexOf("=")
    if ($i -lt 1) { continue }
    $name = $t.Substring(0, $i).Trim()
    $value = $t.Substring($i + 1).Trim()
    if ($value -eq "") { continue }
    # strip optional surrounding quotes
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path "Env:$name" -Value $value
    $loaded += [pscustomobject]@{ variable = $name; len = $value.Length }
}

# The CA bundle is a real file, not a secret, and it goes stale: Avast Web/Mail Shield intercepts
# TLS and re-signs every host with its own root, and when Avast rotates that root the old bundle
# fails n8n, Supabase and Pipedrive alike (2026-09-24, bundle from 2026-08-07). So the bundle is
# healed whenever it is missing OR Windows trusts a certificate the bundle lacks. The same rule
# lives in the Python usercustomize hook; both write the UNION, so they converge, never ping-pong.
if ($env:REQUESTS_CA_BUNDLE) {
    $norm = { param($s) ($s -replace '\s', '') }
    $have = New-Object System.Collections.Generic.HashSet[string]
    $exists = Test-Path $env:REQUESTS_CA_BUNDLE
    if ($exists) {
        $txt = [System.IO.File]::ReadAllText($env:REQUESTS_CA_BUNDLE)
        foreach ($m in [regex]::Matches($txt, '-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----', 'Singleline')) {
            [void]$have.Add((& $norm $m.Groups[1].Value))
        }
    }
    $missing = @()
    foreach ($store in @("Cert:\LocalMachine\Root", "Cert:\CurrentUser\Root",
                         "Cert:\LocalMachine\CA", "Cert:\CurrentUser\CA")) {
        foreach ($c in (Get-ChildItem $store -ErrorAction SilentlyContinue)) {
            try {
                $b64 = [Convert]::ToBase64String($c.RawData)
                if ($have.Add($b64)) { $missing += [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks') }
            } catch {}
        }
    }
    if ($missing.Count -gt 0) {
        $sb = New-Object System.Text.StringBuilder
        if ($exists) { [void]$sb.Append($txt.TrimEnd()); [void]$sb.AppendLine() }
        foreach ($b in $missing) {
            [void]$sb.AppendLine("-----BEGIN CERTIFICATE-----"); [void]$sb.AppendLine($b); [void]$sb.AppendLine("-----END CERTIFICATE-----")
        }
        [System.IO.File]::WriteAllText($env:REQUESTS_CA_BUNDLE, $sb.ToString())
        $why = if ($exists) { "stale ($($missing.Count) cert(s) Windows now trusts were missing - e.g. an Avast root rotation)" } else { "missing" }
        Write-Warning "REQUESTS_CA_BUNDLE was $why - healed $($env:REQUESTS_CA_BUNDLE) from the Windows store"
    }
}

$loaded | Format-Table -AutoSize
Write-Output "loaded $($loaded.Count) variables (values not shown)"
