<?php

/** A version-specific backport. Never apply this to another Coolify release. */
const COOLIFY_HELPER_BASE_SHA256 = [
    'app/Jobs/ApplicationDeploymentJob.php' => '56e49836d9d952e23adb91d6c5c5ed7ad4d2ae7dc32f54c8019ac3879ecae9c8',
    'bootstrap/helpers/docker.php' => 'af3bf14e7d3fef6e5aa1a03ec3cd89fd25afa33877618af8d047068247706467',
];

/** Pure transformation; the CLI always supplies the fixed production hashes. */
function patchCoolifyHelperSources(array $sources, string $retrySource, array $expectedHashes = COOLIFY_HELPER_BASE_SHA256): array
{
    foreach (COOLIFY_HELPER_BASE_SHA256 as $path => $_) {
        if (! isset($sources[$path], $expectedHashes[$path]) || ! hash_equals($expectedHashes[$path], hash('sha256', $sources[$path]))) {
            throw new RuntimeException('Coolify source hash mismatch: '.$path.'. No files changed.');
        }
    }
    if (! str_starts_with($retrySource, "<?php\n") || substr_count($retrySource, 'function dockerRunWithNameConflictRetryCommand(') !== 1) {
        throw new RuntimeException('Invalid helper retry source. No files changed.');
    }

    $jobPath = 'app/Jobs/ApplicationDeploymentJob.php';
    $helperPath = 'bootstrap/helpers/docker.php';
    $job = $sources[$jobPath];
    $oldRun = <<<'PHP'
        $this->graceful_shutdown_container($this->deployment_uuid, skipRemove: true);
        $this->execute_remote_command(
            [
                $runCommand,
                'hidden' => true,
PHP;
    $newRun = str_replace('$runCommand,', 'dockerRunWithNameConflictRetryCommand($runCommand, $this->deployment_uuid),', $oldRun);
    $oldRestart = <<<'PHP'
        // Stop the current helper container (no need for rm -f as it was started with --rm)
        $this->graceful_shutdown_container($this->deployment_uuid, skipRemove: true);

PHP;
    if (substr_count($job, $oldRun) !== 1 || substr_count($job, $oldRestart) !== 1 || str_contains($sources[$helperPath], 'function dockerRunWithNameConflictRetryCommand(')) {
        throw new RuntimeException('Coolify patch anchor mismatch or patch already present. No files changed.');
    }
    $job = str_replace($oldRun, $newRun, $job);
    $job = str_replace($oldRestart, '', $job);
    return [
        $jobPath => $job,
        $helperPath => rtrim($sources[$helperPath], "\n")."\n\n".substr($retrySource, strlen("<?php\n")),
    ];
}

/** Write a fresh output tree only after every source has passed its guard. */
function writeCoolifyHelperPatch(string $sourceRoot, string $outputRoot): void
{
    if (file_exists($outputRoot) || is_link($outputRoot)) {
        throw new RuntimeException('Output already exists; use a fresh output path. No files changed.');
    }
    $sources = [];
    foreach (COOLIFY_HELPER_BASE_SHA256 as $path => $_) {
        $value = @file_get_contents($sourceRoot.'/'.$path);
        if ($value === false) {
            throw new RuntimeException('Missing Coolify input: '.$path.'. No files changed.');
        }
        $sources[$path] = $value;
    }
    $retrySource = file_get_contents(__DIR__.'/helper_retry.php');
    if ($retrySource === false) {
        throw new RuntimeException('Missing helper retry source. No files changed.');
    }
    $patched = patchCoolifyHelperSources($sources, $retrySource);
    $parent = dirname($outputRoot);
    if (! is_dir($parent)) {
        throw new RuntimeException('Output parent must exist. No files changed.');
    }
    $temporary = $parent.'/.coolify-helper-patch-'.bin2hex(random_bytes(8));
    if (! mkdir($temporary, 0700)) {
        throw new RuntimeException('Cannot create patch staging directory.');
    }
    try {
        $hashes = [];
        foreach ($patched as $path => $bytes) {
            if (! mkdir($temporary.'/'.dirname($path), 0755, true) || file_put_contents($temporary.'/'.$path, $bytes, LOCK_EX) !== strlen($bytes)) {
                throw new RuntimeException('Cannot stage patched sources.');
            }
            chmod($temporary.'/'.$path, 0644);
            $hashes[$path] = hash('sha256', $bytes);
        }
        $receipt = json_encode(['schema_version' => 1, 'base_version' => '4.1.2', 'original_sha256' => COOLIFY_HELPER_BASE_SHA256, 'patched_sha256' => $hashes], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)."\n";
        if (file_put_contents($temporary.'/patch-receipt.json', $receipt, LOCK_EX) !== strlen($receipt) || ! rename($temporary, $outputRoot)) {
            throw new RuntimeException('Cannot publish patched output tree.');
        }
    } catch (Throwable $error) {
        // Only this call's random staging tree is eligible for cleanup.
        foreach (array_reverse(array_keys($patched)) as $path) {
            @unlink($temporary.'/'.$path);
        }
        @unlink($temporary.'/patch-receipt.json');
        foreach (['app/Jobs', 'app', 'bootstrap/helpers', 'bootstrap'] as $directory) {
            @rmdir($temporary.'/'.$directory);
        }
        @rmdir($temporary);
        throw $error;
    }
}

if (! defined('COOLIFY_HELPER_PATCH_LIBRARY_ONLY')) {
    try {
        if ($argc !== 3) {
            throw new InvalidArgumentException('Usage: php apply_patch.php SOURCE_ROOT NEW_OUTPUT_ROOT');
        }
        writeCoolifyHelperPatch($argv[1], $argv[2]);
        fwrite(STDOUT, "Verified Coolify 4.1.2 helper patch prepared.\n");
    } catch (Throwable $error) {
        fwrite(STDERR, $error->getMessage()."\n");
        exit(1);
    }
}
