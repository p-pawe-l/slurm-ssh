import unittest
from pyfakefs import fake_filesystem_unittest
from typing import Any

from hpc_con.config.loader import _load_raw_config, _parse_config, read_config

class YamlLoadingConfigTest(fake_filesystem_unittest.TestCase):

    def setUp(self) -> None:
        self.setUpPyfakefs() # Settuping mocked filesystem
        # Creating mocked valid_test_config.yaml for testing 
        self.fs.create_file("valid_test_config.yaml", contents=""" 
            connection:
                host: test.com
                user: test
                port: 22
                key_file: ~/.ssh/id_rsa
            job:
                name: test_job
                commands: test_cmd
        """)

    def test_load_valid_config(self) -> None:
        read_config: dict[str, Any] = _load_raw_config("valid_test_config.yaml")
        expected_config: dict[str, Any] = {
            "connection": {
                "host": "test.com",
                "user": "test",
                "port": 22,
                "key_file": "~/.ssh/id_rsa"
            },
            "job": {
                "name": "test_job",
                "commands": "test_cmd"
            }
        }
        self.assertDictEqual(read_config, expected_config)
        
    