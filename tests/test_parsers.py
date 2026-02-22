"""Unit tests for G-code response parsers."""

from printer_monitor.parsers import parse_m105, parse_m27, parse_m114, parse_m220


class TestParseM105:
    def test_full_response_with_ok(self):
        line = "ok T:204.77 /205.00 B:50.71 /50.00 T0:204.77 /205.00 T1:23.50 /0.00 @:95 B@:0"
        result = parse_m105(line)

        assert result["hotend0"].current == 204.77
        assert result["hotend0"].target == 205.00
        assert result["hotend0"].power == 95

        assert result["hotend1"].current == 23.50
        assert result["hotend1"].target == 0.00

        assert result["bed"].current == 50.71
        assert result["bed"].target == 50.00
        assert result["bed"].power == 0

    def test_response_without_ok(self):
        line = "T:200.00 /210.00 B:60.00 /60.00 T0:200.00 /210.00 T1:25.00 /0.00 @:127 B@:64"
        result = parse_m105(line)

        assert result["hotend0"].current == 200.00
        assert result["hotend0"].target == 210.00
        assert result["hotend0"].power == 127

        assert result["bed"].power == 64

    def test_bare_t_fallback(self):
        """When only T: is present (no T0:), it should be used as hotend0."""
        line = "ok T:204.77 /205.00 B:50.71 /50.00 @:95 B@:0"
        result = parse_m105(line)

        assert result["hotend0"].current == 204.77
        assert result["hotend0"].target == 205.00

    def test_all_heaters_off(self):
        line = "ok T:22.00 /0.00 B:22.00 /0.00 T0:22.00 /0.00 T1:22.00 /0.00 @:0 B@:0"
        result = parse_m105(line)

        assert result["hotend0"].target == 0.00
        assert result["hotend0"].power == 0
        assert result["bed"].target == 0.00

    def test_empty_line(self):
        result = parse_m105("")
        assert result == {}


class TestParseM27:
    def test_printing(self):
        is_printing, done, total = parse_m27("SD printing byte 1234/56789")
        assert is_printing is True
        assert done == 1234
        assert total == 56789

    def test_not_printing(self):
        is_printing, done, total = parse_m27("Not SD printing.")
        assert is_printing is False
        assert done == 0
        assert total == 0

    def test_zero_progress(self):
        is_printing, done, total = parse_m27("SD printing byte 0/56789")
        assert is_printing is True
        assert done == 0
        assert total == 56789

    def test_unknown_format(self):
        is_printing, done, total = parse_m27("ok")
        assert is_printing is False


class TestParseM114:
    def test_standard_response(self):
        line = "X:100.00 Y:50.00 Z:10.50 E:1234.56"
        result = parse_m114(line)

        assert result["x"] == 100.00
        assert result["y"] == 50.00
        assert result["z"] == 10.50
        assert result["e"] == 1234.56

    def test_with_extra_info(self):
        """Marlin may append extra data after the coordinates."""
        line = "X:100.00 Y:50.00 Z:10.50 E:1234.56 Count X:8000 Y:4000 Z:4200"
        result = parse_m114(line)

        assert result["x"] == 100.00
        assert result["y"] == 50.00
        assert result["z"] == 10.50
        assert result["e"] == 1234.56

    def test_negative_coordinates(self):
        line = "X:-5.00 Y:0.00 Z:0.00 E:0.00"
        result = parse_m114(line)
        assert result["x"] == -5.00

    def test_empty_line(self):
        result = parse_m114("")
        assert result == {}


class TestParseM220:
    def test_standard_response(self):
        assert parse_m220("FR:100%") == 100

    def test_modified_feedrate(self):
        assert parse_m220("FR:150%") == 150

    def test_low_feedrate(self):
        assert parse_m220("FR:50%") == 50

    def test_unknown_format(self):
        assert parse_m220("ok") is None

    def test_empty_line(self):
        assert parse_m220("") is None
