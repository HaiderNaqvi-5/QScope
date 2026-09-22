import pytest

from app.services.remediation_executor import (apply_patch, create_checkpoint, rollback_checkpoint,
                                               run_verification_check)


def test_apply_and_rollback_preserve_unrelated_user_change(tmp_path):
    target = tmp_path / "app.py"
    unrelated = tmp_path / "notes.txt"
    target.write_text("value = 1\n")
    unrelated.write_text("my uncommitted work\n")
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
    checkpoint = create_checkpoint(tmp_path, "attempt", ["app.py"], ["python compile"])
    assert apply_patch(tmp_path, patch, checkpoint) == ["app.py"]
    assert target.read_text() == "value = 2\n"
    assert unrelated.read_text() == "my uncommitted work\n"
    restored = rollback_checkpoint(tmp_path, checkpoint)
    assert restored["app.py"] == checkpoint["files"]["app.py"]["sha256"]
    assert target.read_text() == "value = 1\n"
    assert unrelated.read_text() == "my uncommitted work\n"


def test_rollback_removes_only_qsscope_created_file(tmp_path):
    patch = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+value = 1\n"
    checkpoint = create_checkpoint(tmp_path, "attempt", ["new.py"], [])
    apply_patch(tmp_path, patch, checkpoint)
    assert (tmp_path / "new.py").is_file()
    rollback_checkpoint(tmp_path, checkpoint)
    assert not (tmp_path / "new.py").exists()


@pytest.mark.asyncio
async def test_verification_command_is_fixed_vector_and_read_only(tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    result = await run_verification_check(tmp_path, {
        "name": "compile", "argv": ["python", "-m", "py_compile", "app.py"], "timeout_seconds": 10,
    })
    assert result["status"] == "PASSED"
    with pytest.raises(ValueError, match="mutation-capable"):
        await run_verification_check(tmp_path, {"name": "unsafe", "argv": ["npm", "install"]})
