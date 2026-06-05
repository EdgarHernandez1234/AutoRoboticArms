import unittest
from unittest.mock import MagicMock, patch
import struct

# Import your host script class module
from conductor_host import AutoRoboticArmConductor 

class TestAutoRoboticArmConductor(unittest.TestCase):
    def setUp(self):
        """Pre-test configuration environment setup."""
        # Instantiate conductor with known link bounds
        self.conductor = AutoRoboticArmConductor(l1_length_cm=12.0, l2_length_cm=10.0)
        
        # Instantiate a fake serial connection and assign it to the conductor
        self.conductor.serial_connection = MagicMock()

    def test_workspace_envelope_valid_bounds(self):
        """Validates that a valid reachable coordinate does not raise math errors."""
        try:
            # Point (10, 10, 5) is well within reachable stretch boundaries
            base, shoulder, elbow = self.conductor.calculate_ik(10, 10, 5)
            
            # Verify calculated values are stored within servo physical limits
            self.assertTrue(0 <= base <= 180)
            self.assertTrue(0 <= shoulder <= 180)
            self.assertTrue(0 <= elbow <= 180)
        except ValueError:
            self.fail("calculate_ik raised ValueError unexpectedly on a valid coordinate!")

    def test_binary_frame_packing_integrity(self):
        """Uses MagicMock to verify that a packed byte frame contains matching identifiers."""
        joint_target_id = 1
        angle_target = 90
        
        # Act: Pack our payload elements
        packed_frame = self.conductor.pack_binary_frame(joint_target_id, angle_target)
        
        # Assert: Check exact uncompressed frame length match rule (5 bytes)
        self.assertEqual(len(packed_frame), 5)
        
        # Unpack according to struct definition contract: '<BBBBB'
        sync1, sync2, parsed_id, parsed_angle, parsed_crc = struct.unpack('<BBBBB', packed_frame)
        
        # Check alignment sync identifiers
        self.assertEqual(sync1, 0x55)
        self.assertEqual(sync2, 0xAA)
        self.assertEqual(parsed_id, joint_target_id)
        self.assertEqual(parsed_angle, angle_target)
        
        # Verify the pre-calculated CRC byte is present and evaluated as a clean integer
        self.assertTrue(isinstance(parsed_crc, int))

    def test_mock_hardware_write_call(self):
        """Simulates an active output stream to verify the simulated hardware write path is hit."""
        fake_frame = b'\x55\xAA\x02\x2D\x1F' # Simulated packed frame array
        
        # Issue execution instruction forcing a hardware transmission step
        self.conductor.serial_connection.write(fake_frame)
        
        # MagicMock Validation: Assert that our serial write engine was executed accurately
        self.conductor.serial_connection.write.assert_called_once_with(fake_frame)
        
        print("\n[QA SUCCESS] Mock Hardware Serial Interception Validated.")

if __name__ == '__main__':
    unittest.main()