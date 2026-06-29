from ptcg.kaggle_submit_guard import (
    contains_submit_error,
    first_submission_ref,
    main,
    submission_status_for_ref,
)


def test_contains_submit_error_catches_kaggle_400_with_zero_exit_output() -> None:
    output = """
100%|##########| 1.02M/1.02M [00:01<00:00, 663kB/s]
400 Client Error: Bad Request for url: https://api.kaggle.com/v1/competitions.CompetitionApiService/CreateSubmission
"""

    assert contains_submit_error(output)


def test_check_output_catches_powershell_utf16_redirected_kaggle_400(tmp_path) -> None:
    output = tmp_path / "submit.txt"
    output.write_text(
        "400 Client Error: Bad Request for url: https://api.kaggle.com/v1/competitions.CompetitionApiService/CreateSubmission",
        encoding="utf-16",
    )

    assert main(["check-output", "--path", str(output)]) == 1


def test_first_submission_ref_reads_latest_row_from_kaggle_table() -> None:
    table = """
     ref  fileName                                      date                        description  status
--------  --------------------------------------------  --------------------------  -----------  -------------------------
54058466  submission_lucario_meta_edge_tuned.tar.gz     2026-06-25 21:24:43.603000  tuned        SubmissionStatus.COMPLETE
54050856  submission_lucario_loss_guard_iter5.tar.gz    2026-06-25 19:29:07.483000  old          SubmissionStatus.ERROR
"""

    assert first_submission_ref(table) == "54058466"


def test_submission_status_for_ref_extracts_status() -> None:
    table = """
54058466  submission_lucario_meta_edge_tuned.tar.gz  2026-06-25 21:24:43.603000  tuned  SubmissionStatus.COMPLETE  661.5
54050856  submission_lucario_loss_guard_iter5.tar.gz  2026-06-25 19:29:07.483000  old    SubmissionStatus.ERROR
"""

    assert submission_status_for_ref(table, "54058466") == "COMPLETE"
    assert submission_status_for_ref(table, "54050856") == "ERROR"
    assert submission_status_for_ref(table, "123") is None
