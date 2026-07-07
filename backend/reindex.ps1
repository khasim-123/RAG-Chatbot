$env:SSL_CERT_FILE = $null
$env:REQUESTS_CA_BUNDLE = $null
$env:CURL_CA_BUNDLE = $null
$env:PIP_CERT = $null

Write-Host "Cleared CA bundle env vars for this run."
Write-Host "CURL_CA_BUNDLE is now: '$env:CURL_CA_BUNDLE'"

python -m scripts.crawl_and_index --base-url https://vignaniit.edu.in --max-pages 300