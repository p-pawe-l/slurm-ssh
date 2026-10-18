import io
import shlex
import subprocess as sp
import unittest
from contextlib import redirect_stdout
from unittest import mock

from pydantic import ValidationError

from hpc_con.config import ConnectionConfig
from hpc_con.transport import utils

LINUX_SSHD_CHECK: list[str] = ["systemctl", "is-active", "--quiet", "sshd"]
LINUX_SSH_CHECK: list[str] = ["systemctl", "is-active", "--quiet", "ssh"]
DARWIN_CHECK: list[str] = ["launchctl", "print", "system/com.openssh.sshd"]
GENERIC_HINT: str = "see your system's OpenSSH documentation"


class ExecuteLocalCmdTest(unittest.TestCase):

    def setUp(self) -> None:
        self.completed: sp.CompletedProcess[str] = sp.CompletedProcess(
            ["echo", "hi"], 0, stdout="out", stderr="err"
        )
        patcher = mock.patch(
            "hpc_con.transport.utils.sp.run", return_value=self.completed
        )
        self.run: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_wraps_completed_process(self) -> None:
        result: utils.CommandExecutionResult = utils.execute_local_cmd(["echo", "hi"])
        self.assertEqual(result.result_stdout, "out")
        self.assertEqual(result.result_stderr, "err")
        self.assertEqual(result.result_returncode, 0)
        self.assertEqual(result.result_args, ["echo", "hi"])

    def test_runs_argv_list_without_shell(self) -> None:
        utils.execute_local_cmd(["echo", "hi"])
        self.run.assert_called_once_with(
            ["echo", "hi"], capture_output=True, text=True, check=True
        )
        self.assertNotIn("shell", self.run.call_args.kwargs)

    def test_kwargs_are_forwarded(self) -> None:
        utils.execute_local_cmd(["echo", "hi"], timeout=5)
        self.assertEqual(self.run.call_args.kwargs["timeout"], 5)

    def test_nonzero_exit_propagates(self) -> None:
        self.run.side_effect = sp.CalledProcessError(1, ["false"])
        with self.assertRaises(sp.CalledProcessError):
            utils.execute_local_cmd(["false"])


class CommandExecutionResultTest(unittest.TestCase):

    def test_returncode_must_be_strict_int(self) -> None:
        for returncode in ("0", True):
            with (
                self.subTest(returncode=returncode),
                self.assertRaises(ValidationError),
            ):
                utils.CommandExecutionResult(
                    result_stdout="",
                    result_stderr="",
                    result_returncode=returncode,
                    result_args=[],
                )


class BuildSshBaseTest(unittest.TestCase):

    def setUp(self) -> None:
        utils._build_ssh_base.cache_clear()
        self.addCleanup(utils._build_ssh_base.cache_clear)
        self.minimal_config = ConnectionConfig(host="h", user="u")
        self.full_config = ConnectionConfig(
            host="h", user="u", port=2222, key_file="/k"
        )
        self.no_user_config = ConnectionConfig(host="h")

    def test_minimal_config(self) -> None:
        self.assertEqual(
            utils._build_ssh_base(self.minimal_config),
            ["ssh", *utils.SSH_OPTS, "--", "u@h"],
        )

    def test_port_and_key_file_come_before_target(self) -> None:
        argv: list[str] = utils._build_ssh_base(self.full_config)
        self.assertEqual(
            argv, ["ssh", *utils.SSH_OPTS, "-p", "2222", "-i", "/k", "--", "u@h"]
        )

    def test_target_is_last_after_double_dash(self) -> None:
        # A host like "-oProxyCommand=x" can never be read as an ssh option
        argv: list[str] = utils._build_ssh_base(self.full_config)
        self.assertEqual(argv[-2:], ["--", "u@h"])

    def test_batch_mode_is_set(self) -> None:
        # Without BatchMode a password prompt would hang capture_output
        self.assertIn("BatchMode=yes", utils._build_ssh_base(self.minimal_config))

    @unittest.expectedFailure  # bug: target becomes "None@h"
    def test_user_none_omits_user(self) -> None:
        self.assertEqual(utils._build_ssh_base(self.no_user_config)[-1], "h")

    @unittest.expectedFailure  # bug: @cache hands out the same list every call
    def test_returned_list_is_not_shared(self) -> None:
        utils._build_ssh_base(self.minimal_config).append("extra")
        self.assertNotIn("extra", utils._build_ssh_base(self.minimal_config))


class CheckIfSshInstalledTest(unittest.TestCase):

    def setUp(self) -> None:
        patcher = mock.patch("hpc_con.transport.utils.shutil.which")
        self.which: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_passes_when_ssh_on_path(self) -> None:
        self.which.return_value = "/usr/bin/ssh"
        utils._check_if_ssh_installed()
        self.which.assert_called_once_with("ssh")

    def test_raises_with_platform_hint_when_missing(self) -> None:
        self.which.return_value = None
        for platform, hint in utils.SSH_INSTALL_HINTS.items():
            with (
                self.subTest(platform=platform),
                mock.patch.object(utils.sys, "platform", platform),
                self.assertRaises(utils.SSHSetupError) as context,
            ):
                utils._check_if_ssh_installed()
            self.assertIn(hint, str(context.exception))

    def test_generic_hint_on_unknown_platform(self) -> None:
        self.which.return_value = None
        with (
            mock.patch.object(utils.sys, "platform", "win32"),
            self.assertRaises(utils.SSHSetupError) as context,
        ):
            utils._check_if_ssh_installed()
        self.assertIn(GENERIC_HINT, str(context.exception))


class CheckIfSshDaemonIsRunningTest(unittest.TestCase):

    def setUp(self) -> None:
        # Only the fallback loop is tested, result parsing is ExecuteLocalCmdTest
        patcher = mock.patch("hpc_con.transport.utils.execute_local_cmd")
        self.execute: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)
        self.failed = sp.CalledProcessError(3, LINUX_SSHD_CHECK)

    def _check_on(self, platform: str) -> None:
        with mock.patch.object(utils.sys, "platform", platform):
            utils._check_if_ssh_daemon_is_running()

    def test_linux_first_check_succeeds(self) -> None:
        self._check_on("linux")
        self.execute.assert_called_once_with(LINUX_SSHD_CHECK)

    def test_linux_falls_back_to_ssh_unit(self) -> None:
        self.execute.side_effect = [self.failed, None]
        self._check_on("linux")
        self.assertEqual(
            self.execute.call_args_list,
            [mock.call(LINUX_SSHD_CHECK), mock.call(LINUX_SSH_CHECK)],
        )

    def test_linux_all_checks_fail_raises_with_reload_hint(self) -> None:
        self.execute.side_effect = self.failed
        with self.assertRaises(utils.SSHSetupError) as context:
            self._check_on("linux")
        self.assertIn(utils.SSH_RELOAD_HINTS["linux"], str(context.exception))

    def test_missing_systemctl_is_treated_as_down(self) -> None:
        self.execute.side_effect = FileNotFoundError("systemctl")
        with self.assertRaises(utils.SSHSetupError):
            self._check_on("linux")

    def test_darwin_uses_launchctl(self) -> None:
        self._check_on("darwin")
        self.execute.assert_called_once_with(DARWIN_CHECK)

    def test_unknown_platform_raises_without_running_anything(self) -> None:
        with self.assertRaises(utils.SSHSetupError) as context:
            self._check_on("win32")
        self.execute.assert_not_called()
        self.assertIn(GENERIC_HINT, str(context.exception))

    def test_other_errors_propagate(self) -> None:
        self.execute.side_effect = PermissionError()
        with self.assertRaises(PermissionError):
            self._check_on("linux")


class ShowSshSetupTest(unittest.TestCase):

    def setUp(self) -> None:
        self.config = ConnectionConfig(host="h", user="u")
        # Path with a space, the printed command must be shell quoted
        self.argv: list[str] = ["ssh", "-i", "/keys/my key", "--", "u@h"]
        patcher = mock.patch("builtins.input")
        self.input: mock.MagicMock = patcher.start()
        self.addCleanup(patcher.stop)
        self.stdout = io.StringIO()

    def _show(self) -> None:
        with redirect_stdout(self.stdout):
            utils._show_ssh_setup(self.config, self.argv)

    def test_accepts_yes_answers(self) -> None:
        for answer in ("y", "Y", "yes", " YES \n"):
            with self.subTest(answer=answer):
                self.input.return_value = answer
                self._show()

    def test_rejects_everything_else(self) -> None:
        for answer in ("", "n", "no", "yeah", "y y"):
            with self.subTest(answer=answer):
                self.input.return_value = answer
                with self.assertRaises(utils.SSHSetupError):
                    self._show()

    def test_prints_config_and_quoted_command(self) -> None:
        self.input.return_value = "y"
        self._show()
        output: str = self.stdout.getvalue()
        self.assertIn(str(self.config), output)
        self.assertIn(shlex.join(self.argv), output)
        self.assertIn("'/keys/my key'", output)

    @unittest.expectedFailure  # bug: EOFError (no stdin, e.g. CI) escapes
    def test_eof_on_input_raises_setup_error(self) -> None:
        self.input.side_effect = EOFError
        with self.assertRaises(utils.SSHSetupError):
            self._show()
