#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_NAME = "deterministic-port"
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def expected_port(
    hash_input: str,
    range_start: int = 20_000,
    range_size: int = 20_000,
    salt: str = "",
) -> int:
    encoded_input = hash_input.encode()
    if salt:
        encoded_input += b"\0" + salt.encode()
    digest = hashlib.sha256(encoded_input).digest()
    prefix = int.from_bytes(digest[:2], byteorder="big", signed=False)
    return range_start + (prefix % range_size)


class DeterministicPortTests(unittest.TestCase):
    sandbox: tempfile.TemporaryDirectory[str]
    sandbox_path: Path
    mise: str
    mise_env: dict[str, str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.mise = shutil.which("mise") or ""
        if not cls.mise:
            raise unittest.SkipTest("mise is required")
        if not (shutil.which("sha256sum") or shutil.which("shasum")):
            raise unittest.SkipTest("sha256sum or shasum is required")

        cls.sandbox = tempfile.TemporaryDirectory(prefix="deterministic-port-tests-")
        cls.sandbox_path = Path(cls.sandbox.name)
        cls.mise_env = cls._isolated_environment()

        cls._run_mise(
            "plugins",
            "link",
            "--force",
            PLUGIN_NAME,
            str(REPOSITORY_ROOT),
            cwd=cls.sandbox_path,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "sandbox"):
            cls.sandbox.cleanup()

    @classmethod
    def _isolated_environment(cls) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("MISE_")
        }
        environment.update(
            {
                "MISE_CACHE_DIR": str(cls.sandbox_path / "cache"),
                "MISE_CONFIG_DIR": str(cls.sandbox_path / "config"),
                "MISE_DATA_DIR": str(cls.sandbox_path / "data"),
                "MISE_STATE_DIR": str(cls.sandbox_path / "state"),
                "MISE_USE_VERSIONS_HOST": "0",
            }
        )
        return environment

    @classmethod
    def _run_mise(
        cls,
        *arguments: str,
        cwd: Path,
        check: bool = True,
        environment_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = cls.mise_env | {"PWD": str(cwd)}
        if environment_overrides:
            environment.update(environment_overrides)
        result = subprocess.run(
            [cls.mise, *arguments],
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            command = " ".join([cls.mise, *arguments])
            raise AssertionError(
                f"command failed ({result.returncode}): {command}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def _new_project(self, options: str, *, name: str | None = None) -> Path:
        project = self.sandbox_path / "projects" / (name or self.id().split(".")[-1])
        project.mkdir(parents=True, exist_ok=False)
        config = project / "mise.toml"
        config.write_text(
            f"[env]\n_.{PLUGIN_NAME} = {options}\n",
            encoding="utf-8",
        )
        self._run_mise("trust", "--yes", str(config), cwd=self.sandbox_path)
        return project

    def _environment(
        self,
        project: Path,
        *,
        cwd: Path | None = None,
        environment_overrides: dict[str, str] | None = None,
    ) -> dict[str, str]:
        result = self._run_mise(
            "env",
            "--json",
            cwd=cwd or project,
            environment_overrides=environment_overrides,
        )
        return json.loads(result.stdout)

    def _assert_plugin_error(self, options: str, expected_message: str) -> None:
        project = self._new_project(options)
        result = self._run_mise("env", "--json", cwd=project, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected_message, result.stderr)

    def test_default_port_matches_sha256_calculation(self) -> None:
        project = self._new_project("{}")
        environment = self._environment(project)

        self.assertEqual(int(environment["PORT"]), expected_port(str(project)))
        self.assertGreaterEqual(int(environment["PORT"]), 20_000)
        self.assertLessEqual(int(environment["PORT"]), 39_999)

    def test_repeated_activation_is_deterministic(self) -> None:
        project = self._new_project("{}")

        first = self._environment(project)["PORT"]
        second = self._environment(project)["PORT"]

        self.assertEqual(first, second)

    def test_mise_project_root_is_used_from_a_nested_directory(self) -> None:
        project = self._new_project("{}")
        nested = project / "src" / "nested"
        nested.mkdir(parents=True)

        environment = self._environment(
            project,
            cwd=nested,
            environment_overrides={"MISE_PROJECT_ROOT": str(project)},
        )

        self.assertEqual(int(environment["PORT"]), expected_port(str(project)))

    def test_custom_key_and_range(self) -> None:
        hash_input = "/stable/custom-project"
        project = self._new_project(
            '{ key = "DEV_PORT", range_start = 40000, range_size = 1000, '
            f"path = {json.dumps(hash_input)} }}"
        )
        environment = self._environment(project)

        self.assertEqual(
            int(environment["DEV_PORT"]), expected_port(hash_input, 40_000, 1_000)
        )
        self.assertNotIn("PORT", environment)

    def test_multiple_keys_are_consecutive_and_wrap(self) -> None:
        range_size = 3
        hash_input = next(
            candidate
            for index in range(100)
            if expected_port(
                candidate := f"wrap-candidate-{index}", 0, range_size
            )
            == range_size - 1
        )
        project = self._new_project(
            '{ keys = ["WEB_PORT", "API_PORT", "DB_PORT"], '
            f"range_start = 45000, range_size = {range_size}, "
            f"path = {json.dumps(hash_input)} }}"
        )
        environment = self._environment(project)

        self.assertEqual(environment["WEB_PORT"], "45002")
        self.assertEqual(environment["API_PORT"], "45000")
        self.assertEqual(environment["DB_PORT"], "45001")

    def test_keys_take_precedence_over_key(self) -> None:
        project = self._new_project(
            '{ key = "IGNORED_PORT", keys = ["FIRST_PORT", "SECOND_PORT"] }'
        )
        environment = self._environment(project)

        self.assertNotIn("IGNORED_PORT", environment)
        self.assertIn("FIRST_PORT", environment)
        self.assertIn("SECOND_PORT", environment)

    def test_explicit_path_is_stable_across_projects(self) -> None:
        hash_input = "/logical/project/identity"
        options = f"{{ path = {json.dumps(hash_input)} }}"
        first_project = self._new_project(options, name="explicit-path-first")
        second_project = self._new_project(options, name="explicit-path-second")

        first = self._environment(first_project)["PORT"]
        second = self._environment(second_project)["PORT"]

        self.assertEqual(first, second)
        self.assertEqual(int(first), expected_port(hash_input))

    def test_salt_changes_the_hash_deterministically(self) -> None:
        hash_input = "/project/with/a/collision"
        salt = next(
            candidate
            for index in range(100)
            if expected_port(hash_input, salt=(candidate := str(index)))
            != expected_port(hash_input)
        )
        project = self._new_project(
            f"{{ path = {json.dumps(hash_input)}, salt = {json.dumps(salt)} }}"
        )

        first = self._environment(project)["PORT"]
        second = self._environment(project)["PORT"]

        self.assertEqual(int(first), expected_port(hash_input, salt=salt))
        self.assertEqual(first, second)
        self.assertNotEqual(int(first), expected_port(hash_input))

    def test_empty_salt_matches_unsalted_hash(self) -> None:
        hash_input = "/project/with/an/empty/salt"
        project = self._new_project(
            f'{{ path = {json.dumps(hash_input)}, salt = "" }}'
        )

        environment = self._environment(project)

        self.assertEqual(int(environment["PORT"]), expected_port(hash_input))

    def test_salt_works_with_a_custom_range(self) -> None:
        hash_input = "/project/custom-range"
        salt = "collision-2"
        project = self._new_project(
            f"{{ path = {json.dumps(hash_input)}, salt = {json.dumps(salt)}, "
            "range_start = 50000, range_size = 500 }"
        )

        environment = self._environment(project)

        self.assertEqual(
            int(environment["PORT"]),
            expected_port(hash_input, 50_000, 500, salt),
        )

    def test_salt_with_shell_metacharacters_is_not_executed(self) -> None:
        marker = self.sandbox_path / "salt-command-was-executed"
        hash_input = "/project/salted-safely"
        salt = f"$(touch {marker})-'quoted'-$HOME"
        project = self._new_project(
            f"{{ path = {json.dumps(hash_input)}, salt = {json.dumps(salt)} }}"
        )

        environment = self._environment(project)

        self.assertEqual(
            int(environment["PORT"]), expected_port(hash_input, salt=salt)
        )
        self.assertFalse(marker.exists())

    def test_path_with_shell_metacharacters_is_not_executed(self) -> None:
        marker = self.sandbox_path / "command-was-executed"
        hash_input = f"project-$(touch {marker})-'quoted'-$HOME"
        project = self._new_project(f"{{ path = {json.dumps(hash_input)} }}")

        environment = self._environment(project)

        self.assertEqual(int(environment["PORT"]), expected_port(hash_input))
        self.assertFalse(marker.exists())

    def test_rejects_empty_keys(self) -> None:
        self._assert_plugin_error(
            "{ keys = [] }", "keys must be a non-empty array"
        )

    def test_rejects_non_array_keys(self) -> None:
        self._assert_plugin_error(
            '{ keys = "PORT" }', "keys must be a non-empty array"
        )

    def test_rejects_invalid_environment_variable_name(self) -> None:
        self._assert_plugin_error(
            '{ key = "INVALID-NAME" }', "invalid environment variable name"
        )

    def test_rejects_non_integer_range_start(self) -> None:
        self._assert_plugin_error(
            "{ range_start = 20000.5 }", "range_start must be an integer"
        )

    def test_rejects_non_string_salt(self) -> None:
        self._assert_plugin_error("{ salt = 2 }", "salt must be a string")

    def test_rejects_non_integer_range_size(self) -> None:
        self._assert_plugin_error(
            "{ range_size = 10.5 }", "range_size must be an integer"
        )

    def test_rejects_range_start_below_valid_ports(self) -> None:
        self._assert_plugin_error(
            "{ range_start = 0 }", "range_start must be between 1 and 65535"
        )

    def test_rejects_range_start_above_valid_ports(self) -> None:
        self._assert_plugin_error(
            "{ range_start = 65536 }", "range_start must be between 1 and 65535"
        )

    def test_rejects_range_smaller_than_key_count(self) -> None:
        self._assert_plugin_error(
            '{ keys = ["ONE_PORT", "TWO_PORT"], range_size = 1 }',
            "range_size must be at least the number of requested keys",
        )

    def test_rejects_range_ending_above_largest_port(self) -> None:
        self._assert_plugin_error(
            "{ range_start = 65530, range_size = 10 }",
            "configured port range must end at or before 65535",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
