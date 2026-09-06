from cs2bot.gamestate import GSI_CFG_NAME, gsi_endpoint, inspect_gsi_cfg, install_gsi_cfg


def cfg_dir(tmp_path):
    directory = tmp_path / "csgo" / "cfg"
    directory.mkdir(parents=True)
    return directory


def test_a_freshly_installed_config_has_nothing_wrong_with_it(tmp_path):
    directory = cfg_dir(tmp_path)
    endpoint = gsi_endpoint(8420)
    install_gsi_cfg(directory, endpoint, auth_token="hunter2")
    assert inspect_gsi_cfg(directory, endpoint, "hunter2") == []


def test_an_unset_or_missing_directory_is_the_only_complaint(tmp_path):
    assert inspect_gsi_cfg("", gsi_endpoint(8420)) == [
        "the CS2 cfg directory is not set on the Game tab"
    ]
    missing = inspect_gsi_cfg(tmp_path / "nope", gsi_endpoint(8420))
    assert len(missing) == 1 and "does not exist" in missing[0]


def test_the_wrong_folder_and_a_missing_config_are_both_reported(tmp_path):
    stray = tmp_path / "Steam" / "cfg"
    stray.mkdir(parents=True)
    (stray / "gamestate_integration_aurora.cfg").write_text("{}", encoding="utf-8")

    problems = inspect_gsi_cfg(stray, gsi_endpoint(8420))
    assert len(problems) == 2
    assert "game/csgo/cfg" in problems[0]
    assert GSI_CFG_NAME in problems[1] and "gamestate_integration_aurora.cfg" in problems[1]


def test_a_config_from_another_port_or_token_asks_to_be_reinstalled(tmp_path):
    directory = cfg_dir(tmp_path)
    install_gsi_cfg(directory, gsi_endpoint(3000), auth_token="old")

    problems = inspect_gsi_cfg(directory, gsi_endpoint(8420), "new")
    assert len(problems) == 2
    assert all("reinstall" in problem for problem in problems)


def test_the_endpoint_is_loopback_whatever_the_panel_binds_to():
    assert gsi_endpoint(8420) == "http://127.0.0.1:8420/api/gsi"
