import os
import unittest
from typing import Any
from unittest import mock

from pyfakefs import fake_filesystem_unittest

from hpc_con.config import ConnectionConfig, HPC_ConConfig, InvalidConfigError
from hpc_con.config.loader import _load_raw_config, _parse_config, read_config
from hpc_con.job import HPCJob


class LoadRawConfigTest(fake_filesystem_unittest.TestCase):

    def setUp(self) -> None:
        self.setUpPyfakefs()  # Settuping mocked filesystem
        # Creating mocked valid_test_config.yaml for testing
        self.fs.create_file(
            "valid_test_config.yaml",
            contents="""
            connection:
                host: test.com
                user: test
                port: 22
                key_file: ~/.ssh/id_rsa
            job:
                name: test_job
                commands: test_cmd
        """,
        )
        self.fs.create_file("empty_test_config.yaml", contents="")
        self.fs.create_file(
            "invalid_test_config.yaml",
            contents="""
            gowno: gowno: gowno
            dupa: dupa_val
        """,
        )
        self.fs.create_file("list_test_config.yaml", contents="- a\n- b\n")
        self.fs.create_file("scalar_test_config.yaml", contents="just text\n")

    def test_load_valid_config(self) -> None:
        read_config: dict[str, Any] = _load_raw_config("valid_test_config.yaml")
        expected_config: dict[str, Any] = {
            "connection": {
                "host": "test.com",
                "user": "test",
                "port": 22,
                "key_file": "~/.ssh/id_rsa",
            },
            "job": {"name": "test_job", "commands": "test_cmd"},
        }
        self.assertDictEqual(read_config, expected_config)

    def test_load_empty_config(self) -> None:
        read_config: dict[str, Any] = _load_raw_config("empty_test_config.yaml")
        self.assertDictEqual(read_config, {})

    def test_load_invalid_config(self) -> None:
        # Should raise on gowno: gowno: gowno in YAML file
        self.assertRaises(
            InvalidConfigError, _load_raw_config, "invalid_test_config.yaml"
        )

    def test_invalid_yaml_error_names_source_and_yaml_path(self) -> None:
        with self.assertRaises(InvalidConfigError) as context:
            _load_raw_config("invalid_test_config.yaml")
        self.assertEqual(context.exception.errors[0].path, "<yaml>")
        self.assertIn("invalid_test_config.yaml", str(context.exception))

    def test_missing_file_raises_file_not_found(self) -> None:
        # The CLI catches OSError, so the loader must not wrap this one
        with self.assertRaises(FileNotFoundError):
            _load_raw_config("does_not_exist.yaml")

    def test_list_at_root_is_returned_unchanged(self) -> None:
        # validate_config rejects it later, the loader only reads
        self.assertEqual(_load_raw_config("list_test_config.yaml"), ["a", "b"])

    def test_scalar_at_root_is_returned_unchanged(self) -> None:
        self.assertEqual(_load_raw_config("scalar_test_config.yaml"), "just text")


class ParseConfigTest(unittest.TestCase):

    def _config(self, **job: Any) -> dict[str, Any]:
        """Minimal config that passed validate_config, extra job keys merged in."""
        return {
            "connection": {"host": "test.com"},
            "job": {"name": "test_job", "commands": ["test_cmd"], **job},
        }

    def test_builds_dataclasses(self) -> None:
        config: HPC_ConConfig = _parse_config(self._config())
        self.assertEqual(config.connection, ConnectionConfig(host="test.com"))
        self.assertEqual(config.job, HPCJob(name="test_job", commands=["test_cmd"]))

    def test_missing_optional_keys_use_defaults(self) -> None:
        config: HPC_ConConfig = _parse_config(self._config())
        self.assertIsNone(config.connection.user)
        self.assertIsNone(config.connection.port)
        self.assertIsNone(config.connection.key_file)
        self.assertEqual(config.job.time, "01:00:00")
        self.assertEqual(config.job.nodes, 1)
        self.assertEqual(config.job.modules, [])
        self.assertEqual(config.job.env, {})

    @mock.patch.dict(os.environ, {"HOME": "/home/test"})
    def test_key_file_tilde_is_expanded(self) -> None:
        raw: dict[str, Any] = self._config()
        raw["connection"]["key_file"] = "~/.ssh/id_rsa"
        config: HPC_ConConfig = _parse_config(raw)
        self.assertEqual(config.connection.key_file, "/home/test/.ssh/id_rsa")

    def test_numeric_mem_becomes_string(self) -> None:
        config: HPC_ConConfig = _parse_config(self._config(mem=16))
        self.assertEqual(config.job.mem, "16")

    def test_env_values_become_strings(self) -> None:
        config: HPC_ConConfig = _parse_config(
            self._config(env={"OMP_NUM_THREADS": 8, "WANDB_MODE": "offline"})
        )
        self.assertEqual(
            config.job.env, {"OMP_NUM_THREADS": "8", "WANDB_MODE": "offline"}
        )

    def test_input_dict_is_not_modified(self) -> None:
        raw: dict[str, Any] = self._config(mem=16)
        _parse_config(raw)
        self.assertEqual(raw["job"]["mem"], 16)


@mock.patch.dict(os.environ, {"HOME": "/home/test"})
class ReadConfigTest(fake_filesystem_unittest.TestCase):

    def setUp(self) -> None:
        self.setUpPyfakefs()  # Settuping mocked filesystem
        # Key file referenced by the configs below as ~/.ssh/id_rsa
        self.fs.create_file("/home/test/.ssh/id_rsa")
        self.fs.create_file(
            "valid_test_config.yaml",
            contents="""
            connection:
                host: test.com
                user: test
                key_file: ~/.ssh/id_rsa
            job:
                name: test_job
                commands: [test_cmd]
                mem: 16G
        """,
        )
        self.fs.create_file("empty_test_config.yaml", contents="")
        # Missing host and name, port has the wrong type
        self.fs.create_file(
            "structure_errors_test_config.yaml",
            contents="""
            connection:
                port: not_a_number
            job:
                commands: [test_cmd]
        """,
        )
        self.fs.create_file(
            "missing_key_file_test_config.yaml",
            contents="""
            connection:
                host: test.com
                key_file: ~/.ssh/missing
            job:
                name: test_job
                commands: [test_cmd]
        """,
        )
        # Structure is fine, but the name fails the job regex
        self.fs.create_file(
            "bad_job_name_test_config.yaml",
            contents="""
            connection:
                host: test.com
            job:
                name: "bad name; rm -rf"
                commands: [test_cmd]
        """,
        )

    def test_valid_config_is_parsed(self) -> None:
        config: HPC_ConConfig = read_config("valid_test_config.yaml")
        self.assertEqual(config.connection.key_file, "/home/test/.ssh/id_rsa")
        self.assertEqual(config.job.commands, ["test_cmd"])
        self.assertEqual(config.job.mem, "16G")

    def test_empty_config_reports_missing_sections(self) -> None:
        with self.assertRaises(InvalidConfigError) as context:
            read_config("empty_test_config.yaml")
        paths: list[str] = [error.path for error in context.exception.errors]
        self.assertEqual(sorted(paths), ["connection", "job"])

    def test_structure_errors_are_collected_together(self) -> None:
        with self.assertRaises(InvalidConfigError) as context:
            read_config("structure_errors_test_config.yaml")
        paths: list[str] = [error.path for error in context.exception.errors]
        self.assertIn("connection.host", paths)
        self.assertIn("connection.port", paths)
        self.assertIn("job.name", paths)
        self.assertIn("structure_errors_test_config.yaml", str(context.exception))

    def test_missing_key_file_is_reported(self) -> None:
        with self.assertRaises(InvalidConfigError) as context:
            read_config("missing_key_file_test_config.yaml")
        paths: list[str] = [error.path for error in context.exception.errors]
        self.assertEqual(paths, ["connection.key_file"])

    def test_job_value_errors_are_reported_under_job(self) -> None:
        with self.assertRaises(InvalidConfigError) as context:
            read_config("bad_job_name_test_config.yaml")
        self.assertTrue(context.exception.errors)
        for error in context.exception.errors:
            self.assertEqual(error.path, "job")
