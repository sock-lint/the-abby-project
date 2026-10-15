<?php

/**
 * Retry only Docker's unambiguous failure to reserve this helper's name.
 * No remove, rename, inspect, or unrelated deployment operation is retried.
 */
function dockerRunWithNameConflictRetryCommand(string $command, string $container, int $timeout = 60): string
{
    if (! preg_match('/\A[a-zA-Z0-9][a-zA-Z0-9_.-]*\z/', $container) || $timeout < 1 || $timeout > 60) {
        throw new InvalidArgumentException('Invalid helper retry parameters.');
    }

    $conflict = escapeShellValue('Conflict. The container name "/'.$container.'" is already in use by container "');
    $message = escapeShellValue("Timed out waiting for Docker to release helper name {$container}; existing container preserved.");
    // A fresh bash process starts SECONDS at zero. Avoid arithmetic expansion:
    // Coolify 4.1.2's non-root sudo parser rewrites command-substitution prefixes.
    $script = 'while true; do '
        .'output=$('.$command.' 2>&1); exit_code=$?; '
        .'if [ "$exit_code" -eq 0 ]; then printf \'%s\\n\' "$output"; exit 0; fi; '
        .'if [ "$exit_code" -ne 125 ]; then printf \'%s\\n\' "$output" >&2; exit "$exit_code"; fi; '
        .'case "$output" in *'.$conflict.'*) '
        .'if [ "$SECONDS" -ge "'.$timeout.'" ]; then printf \'%s\\n\' '.$message.' >&2; exit 124; fi; '
        .'sleep 0.1 ;; *) printf \'%s\\n\' "$output" >&2; exit "$exit_code" ;; esac; done';

    return 'bash -c '.escapeShellValue($script);
}
