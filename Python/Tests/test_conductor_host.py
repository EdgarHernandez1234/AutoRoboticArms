import unittest
from unittest.mock import MagicMock
# Assuming your file is named conductor_host.py
from conductor_host import ConductorHost

class TestConductorHost(unittest.TestCase):
    def setUp(self):
        """Instantiates a test case handler with a mocked hardware serial interface."""
        # We mock the port so it doesn't try to open an actual physical serial device during evaluation
        self.host = ConductorHost(port="MOCK_PORT", baudrate=115200)
        self.host.connection = MagicMock()

    def test_checksum_calculation_valid(self):
        """Validates that the mathematical XOR algorithm matches manually derived values."""
        payload = "DRV,90,45"
        # Manually calculating XOR: 'D'^'R'^'V'^','^'9'^'0'^','^'4'^'5' = 0x4A
        expected_checksum = "4A"
        calculated = self.host.calculate_xor_checksum(payload)
        self.assertEqual(calculated, expected_checksum, "Checksum mathematical calculation failed.")

    def test_checksum_calculation_edge_case_zeros(self):
        """Verifies parity logic remains stable at baseline initialization boundaries."""
        payload = "DRV,0,0"
        # 'D'^'R'^'V'^','^'0'^','^'0' = 0x1D
        expected_checksum = "1D"
        calculated = self.host.calculate_xor_checksum(payload)
        self.assertEqual(calculated, expected_checksum)

    def test_packet_formatting_structure(self):
        """Ensures that the emitted string explicitly respects the framing contract wrappers."""
        self.host.connection.is_open = True
        
        # Trigger the transmission method execution
        self.host.send_command("DRV", 90, 45)
        
        # Check what was passed down to the connection's write method
        self.host.connection.write.assert_called_once()
        raw_emitted_bytes = self.host.connection.write.call_args[0][0]
        emitted_string = raw_emitted_bytes.decode('ascii')
        
        # Assert structural contract alignment
        self.assertTrue(emitted_string.startswith("@"), "Packet missing start marker '@'")
        self.assertTrue(emitted_string.endswith("\n"), "Packet missing terminator newline '\\n'")
        self.assertIn("*4A", emitted_string, "Packet checksum missing or invalid.")

if __name__ == "__main__":
    unittest.main()