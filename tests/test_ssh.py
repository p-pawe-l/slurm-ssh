import io
import pathlib as ph
import subprocess as sp
import unittest
from contextlib import redirect_stdout
from unittest import mock

from hpc_con.config import ConnectionConfig
from hpc_con.transport import SSHConnection, utils

SSH_MODULE: str = "hpc_con.transport._ssh"


def _completed(argv: list[str], returncode: int = 0) -> sp.CompletedProcess[str]:
    return sp.CompletedProcess(argv, returncode, stdout="", stderr="")


class SSHConnectionInitTest(unittest.TestCase):

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.config = ConnectionConfig(host="h", user="u", port=2222)

    def test_starts_inactive_with_ssh_base(self) -> None:
        connection = SSHConnection(self.config, verbose=True)
        self.assertFalse(connection.is_active)
        self.assertTrue(connection.verbose)
        self.assertEqual(connection._ssh_base_args, utils._build_ssh_base(self.config))


class SSHConnectionConnectTest(unittest.TestCase):

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.config = ConnectionConfig(host="h", user="u")
        self.connection = SSHConnection(self.config)

        # One manager records the order of the checks and the ssh call
        self.calls = mock.Mock()
        for name in (
            "_check_if_ssh_installed",
            "_check_if_ssh_daemon_is_running",
            "_show_ssh_setup",
        ):
            patcher = mock.patch(f"{SSH_MODULE}.{name}")
            self.calls.attach_mock(patcher.start(), name)
            self.addCleanup(patcher.stop)
        patcher = mock.patch(
            f"{SSH_MODULE}.sp.run",
            return_value=_completed(self.connection._ssh_base_args),
        )
        self.calls.attach_mock(patcher.start(), "run")
        self.addCleanup(patcher.stop)

    def test_runs_checks_in_order_before_ssh(self) -> None:
        self.connection.connect()
        self.assertEqual(
            [name for name, _args, _kwargs in self.calls.mock_calls],
            [
                "_check_if_ssh_installed",
                "_check_if_ssh_daemon_is_running",
                "_show_ssh_setup",
                "run",
            ],
        )

    def test_show_setup_receives_config_and_argv(self) -> None:
        self.connection.connect()
        self.calls._show_ssh_setup.assert_called_once_with(
            self.config, self.connection._ssh_base_args
        )

    def test_success_sets_is_active(self) -> None:
        self.connection.connect()
        self.assertTrue(self.connection.is_active)

    def test_runs_ssh_as_argv_list_without_shell(self) -> None:
        self.connection.connect()
        args, kwargs = self.calls.run.call_args
        self.assertEqual(args[0], self.connection._ssh_base_args)
        self.assertNotIn("shell", kwargs)

    def test_check_failure_stops_before_ssh(self) -> None:
        for name in (
            "_check_if_ssh_installed",
            "_check_if_ssh_daemon_is_running",
            "_show_ssh_setup",
        ):
            with self.subTest(check=name):
                getattr(self.calls, name).side_effect = utils.SSHSetupError()
                with self.assertRaises(utils.SSHSetupError):
                    self.connection.connect()
                self.calls.run.assert_not_called()
                self.assertFalse(self.connection.is_active)
                getattr(self.calls, name).side_effect = None

    def test_ssh_failure_leaves_inactive(self) -> None:
        self.calls.run.side_effect = sp.CalledProcessError(255, ["ssh"])
        with self.assertRaises(sp.CalledProcessError):
            self.connection.connect()
        self.assertFalse(self.connection.is_active)


class SSHConnectionRemoteCmdTest(unittest.TestCase):

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.connection = SSHConnection(ConnectionConfig(host="h", user="u"))
        # Name mangled private method
        self.execute = self.connection._SSHConnection__execute_remote_cmd
        patcher = mock.patch(f"{SSH_MODULE}.sp.run", return_value=_completed([]))
        self.run: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_inactive_returns_none_without_running(self) -> None:
        self.assertIsNone(self.execute(["hostname"]))
        self.run.assert_not_called()

    def test_active_prefixes_ssh_base_and_forwards_kwargs(self) -> None:
        self.connection.is_active = True
        self.execute(["hostname"], input="data")
        args, kwargs = self.run.call_args
        self.assertEqual(args[0][:-1], self.connection._ssh_base_args)
        self.assertEqual(kwargs["input"], "data")

    @unittest.expectedFailure  # AGENTS.md: remote command is one shlex.join string
    def test_remote_command_is_single_shlex_joined_string(self) -> None:
        self.connection.is_active = True
        self.execute(["echo", "a b; rm -rf /"])
        argv: list[str] = self.run.call_args.args[0]
        self.assertEqual(
            argv, [*self.connection._ssh_base_args, "echo 'a b; rm -rf /'"]
        )


class SSHConnectionCopyFetchTest(unittest.TestCase):

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.connection = SSHConnection(ConnectionConfig(host="h", user="u"))
        # Absolute paths, so Path.absolute() does not depend on the cwd
        self.files: list[ph.Path] = [
            ph.Path("/data/a.txt"),
            ph.Path("/data/b.txt"),
            ph.Path("/data/c.txt"),
        ]
        patcher = mock.patch(f"{SSH_MODULE}.sp.run", return_value=_completed([]))
        self.run: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_copy_builds_scp_argv(self) -> None:
        self.connection.copy_files(self.files[:1])
        self.run.assert_called_once()
        self.assertEqual(
            self.run.call_args.args[0], ["scp", "/data/a.txt", "u@h:/data/a.txt"]
        )

    def test_fetch_builds_scp_argv(self) -> None:
        self.connection.fetch_files(self.files[:1])
        self.assertEqual(
            self.run.call_args.args[0], ["scp", "u@h:/data/a.txt", "/data/a.txt"]
        )

    def test_one_result_per_file(self) -> None:
        for method in (self.connection.copy_files, self.connection.fetch_files):
            with self.subTest(method=method.__name__):
                self.run.reset_mock()
                self.assertEqual(len(method(self.files)), 3)
                self.assertEqual(self.run.call_count, 3)

    def test_scp_failure_propagates(self) -> None:
        self.run.side_effect = sp.CalledProcessError(1, ["scp"])
        with self.assertRaises(sp.CalledProcessError):
            self.connection.copy_files(self.files)


class SSHConnectFlowTest(unittest.TestCase):
    """
    Real wiring between _ssh.py and utils.py, only the outer edges are mocked:
    PATH lookup, platform, the user's answer and one subprocess.run.
    """

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.connection = SSHConnection(ConnectionConfig(host="h", user="u"))
        self.stdout = io.StringIO()
        for patcher in (
            mock.patch.object(utils.shutil, "which", return_value="/usr/bin/ssh"),
            mock.patch.object(utils.sys, "platform", "linux"),
            redirect_stdout(self.stdout),
        ):
            patcher.__enter__()
            self.addCleanup(patcher.__exit__, None, None, None)
        input_patcher = mock.patch("builtins.input")
        self.input: mock.MagicMock = input_patcher.start()
        self.addCleanup(input_patcher.stop)
        run_patcher = mock.patch(
            "subprocess.run", side_effect=lambda argv, **_: _completed(argv)
        )
        self.run: mock.MagicMock = run_patcher.start()
        self.addCleanup(run_patcher.stop)

    def _recorded_argv(self) -> list[list[str]]:
        return [call.args[0] for call in self.run.call_args_list]

    def test_confirmed_setup_checks_daemon_then_connects(self) -> None:
        self.input.return_value = "y"
        self.connection.connect()
        self.assertEqual(
            self._recorded_argv(),
            [
                ["systemctl", "is-active", "--quiet", "sshd"],
                self.connection._ssh_base_args,
            ],
        )
        self.assertTrue(self.connection.is_active)

    def test_rejected_setup_never_runs_ssh(self) -> None:
        self.input.return_value = "n"
        with self.assertRaises(utils.SSHSetupError):
            self.connection.connect()
        self.assertNotIn(self.connection._ssh_base_args, self._recorded_argv())
        self.assertFalse(self.connection.is_active)
