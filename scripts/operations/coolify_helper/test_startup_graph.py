"""Regression checks for the candidate's offline s6 graph acceptance."""

import unittest

from verify_startup_graph import REQUIRED_DEPENDENCIES, parse_and_validate_dependencies


def graph_output(dependencies):
    return "\n".join(
        [line for service, values in dependencies.items()
         for line in [f"__S6_DEPS__ {service}", *sorted(values)]]
    )


class StartupGraphTests(unittest.TestCase):
    def test_complete_required_chain_is_accepted(self):
        parsed = parse_and_validate_dependencies(graph_output(REQUIRED_DEPENDENCIES))
        self.assertEqual(set(parsed["nginx"]), {"php-fpm", "init-script"})

    def test_dependencies_directory_hiding_flat_file_is_rejected(self):
        dependencies = {service: set(values) for service, values in REQUIRED_DEPENDENCIES.items()}
        dependencies["nginx"].remove("php-fpm")
        with self.assertRaisesRegex(ValueError, "nginx dependencies missing: php-fpm"):
            parse_and_validate_dependencies(graph_output(dependencies))

    def test_ingress_not_waiting_for_init_is_rejected(self):
        dependencies = {service: set(values) for service, values in REQUIRED_DEPENDENCIES.items()}
        dependencies["php-fpm"].clear()
        with self.assertRaisesRegex(ValueError, "php-fpm dependencies missing: init-script"):
            parse_and_validate_dependencies(graph_output(dependencies))


if __name__ == "__main__":
    unittest.main()
