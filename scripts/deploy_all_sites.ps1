# Merge main into every site branch and push to GitHub.
# Railway auto-deploys each service when its tracked branch updates.
#
# Usage (from repo root):
#   .\scripts\deploy_all_sites.ps1
#
# What it does for each branch in $branches:
#   1. git checkout <branch>
#   2. git pull (sync with remote)
#   3. git merge main (fast-forward or merge commit)
#   4. On non-SE branches: remove bundled_data/ (mshop.se-specific
#      data that would contaminate the DK/EU services if loaded).
#      persistence.py also respects SKIP_BUNDLED_DATA=1 as belt-and-
#      braces — set that env var on the DK/EU Railway services too.
#   5. git push origin <branch>
#   6. Return to whatever branch the user started on.
#
# If any branch has a conflict, the script stops and you finish that
# branch manually — the remaining branches are not touched until you
# fix and re-run.

$ErrorActionPreference = "Stop"  # any git error halts the script

# NOTE: mshop-se is intentionally NOT here. The SE Railway service
# watches `main` directly, so pushing to main is enough — no separate
# branch needed. If you later create an mshop-se branch (for full
# parity with the other shops), add it here.
$branches = @("mshop-dk", "mshop-eu")

# Remember where the user was so we restore at the end
$startBranch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host ""
Write-Host "Starting from branch: ${startBranch}" -ForegroundColor Cyan
Write-Host ""

# Make sure main is up to date locally
Write-Host "Updating main from remote..." -ForegroundColor Cyan
git checkout main
git pull origin main
Write-Host ""

foreach ($b in $branches) {
    Write-Host "=== ${b} ===" -ForegroundColor Yellow

    # Check the branch exists locally (or on remote)
    $localExists = (git branch --list $b) -ne ""
    if (-not $localExists) {
        Write-Host "  Branch '${b}' does not exist locally - skipping." -ForegroundColor DarkYellow
        Write-Host "  (Create it: git checkout -b ${b} ; git push -u origin ${b})" -ForegroundColor DarkGray
        continue
    }

    git checkout $b
    git pull origin $b
    git merge main --no-edit

    # bundled_data/ no longer needs special cleanup. Files are now suffixed
    # with the shop code (sf_pages_se.csv.gz, etc.) and persistence.py only
    # loads files matching the service's SITE_CODE env var. SE files merged
    # to DK/EU branches sit on disk but are never loaded → no contamination.
    # Each shop's own data lives only on its branch (e.g. sf_pages_dk.csv.gz
    # only on mshop-dk) because main never gets cross-shop data merged back.

    git push origin $b
    Write-Host "  ${b} updated and pushed." -ForegroundColor Green
    Write-Host ""
}

# Restore the user's original branch
Write-Host "Returning to ${startBranch}..." -ForegroundColor Cyan
git checkout $startBranch
Write-Host ""
Write-Host "Done. Railway will redeploy each service automatically." -ForegroundColor Green
