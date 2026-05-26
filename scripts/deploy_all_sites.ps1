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
#   4. git push origin <branch>
#   5. Return to wherever you were before running
#
# If any branch has a conflict, the script stops and you finish that
# branch manually — the remaining branches are not touched until you
# fix and re-run. Safer than blindly continuing.

$ErrorActionPreference = "Stop"  # any git error halts the script

$branches = @("mshop-se", "mshop-dk", "mshop-eu")

# Remember where the user was so we restore at the end
$startBranch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host ""
Write-Host "Starting from branch: $startBranch" -ForegroundColor Cyan
Write-Host ""

# Make sure main is up to date locally
Write-Host "Updating main from remote..." -ForegroundColor Cyan
git checkout main
git pull origin main
Write-Host "  main is at $(git rev-parse --short HEAD)" -ForegroundColor Gray
Write-Host ""

foreach ($b in $branches) {
    Write-Host "=== $b ===" -ForegroundColor Yellow

    # Check the branch exists locally (or on remote)
    $localExists = (git branch --list $b) -ne ""
    if (-not $localExists) {
        Write-Host "  Branch '$b' does not exist locally — skipping." -ForegroundColor DarkYellow
        Write-Host "  (Create it first: git checkout -b $b; git push -u origin $b)" -ForegroundColor DarkGray
        continue
    }

    git checkout $b
    git pull origin $b
    git merge main --no-edit
    git push origin $b
    Write-Host "  $b updated and pushed." -ForegroundColor Green
    Write-Host ""
}

# Restore the user's original branch
Write-Host "Returning to $startBranch..." -ForegroundColor Cyan
git checkout $startBranch
Write-Host ""
Write-Host "Done. Railway will redeploy each service automatically." -ForegroundColor Green
