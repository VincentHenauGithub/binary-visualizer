import sys
import os
import argparse
import struct
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPlainTextEdit, QComboBox, QPushButton, QLabel, QSizePolicy)
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import Qt, pyqtSignal


# Argument Parsing
parser = argparse.ArgumentParser(description='Hex Viewer')
parser.add_argument('-f', '--file_path', required=True, help='Path to the file to display')
parser.add_argument('-i', '--index', type=int, default=0, help='Index to highlight (default is 0)')
args = parser.parse_args()


class CustomTextEdit(QPlainTextEdit):
    """
    Subclass of QPlainTextEdit that emits a signal when the mouse is released,
    indicating that the user has finished making a selection.
    """
    selectionFinished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.selectionFinished.emit()


class MainWindow(QMainWindow):
    def __init__(self, data, index):
        super().__init__()
        self.data = data
        self.index = index
        self.original_index = index  # Keep track of the original index
        self.syncing_scroll = False  # Flag to prevent recursive scrolling
        self.syncing_selection = False  # Flag to prevent recursive selection synchronization
        self.hex_positions = []  # Mapping of byte index to hex_view text position
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Hex Viewer')

        # Set dark theme and better font
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #dcdcdc;
            }
            QLabel {
                background-color: #2b2b2b;
                color: #dcdcdc;
                font-family: 'Consolas';
                font-size: 12px;
            }
            QPlainTextEdit {
                background-color: #3c3f41;
                color: #dcdcdc;
                font-family: 'Consolas';
                font-size: 12px;
            }
            QComboBox, QPushButton {
                background-color: #3c3f41;
                color: #dcdcdc;
                font-family: 'Consolas';
                font-size: 12px;
            }
        """)

        # Create main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Create main vertical layout
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Create horizontal layout for top panes
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        # Left pane: headers and hex bytes
        left_pane = QVBoxLayout()
        top_layout.addLayout(left_pane)

        # Headers Layout
        headers_layout = QVBoxLayout()
        left_pane.addLayout(headers_layout)

        # Decimal Header
        self.decimal_header = QLabel()
        self.decimal_header.setAlignment(Qt.AlignLeft)
        self.setupDecimalHeader()
        headers_layout.addWidget(self.decimal_header)

        # Hexadecimal Header
        self.hex_header = QLabel()
        self.hex_header.setAlignment(Qt.AlignLeft)
        self.setupHexHeader()
        headers_layout.addWidget(self.hex_header)
        
        self.spacer = QLabel()
        self.spacer.setFixedHeight(7)
        self.spacer.setStyleSheet("background-color: #2b2b2b;")
        headers_layout.addWidget(self.spacer)

        # Hex view
        self.hex_view = CustomTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setFont(QFont('Consolas', 10))  # Monospace font
        self.hex_view.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)  # Fixed width
        self.hex_view.setFixedWidth(self.calculateHexViewWidth())
        self.hex_view.setFixedHeight(400)
        self.hex_view.setLineWrapMode(QPlainTextEdit.NoWrap)  # Disable line wrapping
        left_pane.addWidget(self.hex_view)

        # Right pane: string representation and data types
        right_pane = QVBoxLayout()
        top_layout.addLayout(right_pane)

        # Data type selection
        self.data_type_combo = QComboBox()
        self.data_type_combo.addItem('ASCII')
        self.data_type_combo.addItem('8-bit int')
        self.data_type_combo.addItem('16-bit int')
        self.data_type_combo.addItem('32-bit int')
        self.data_type_combo.addItem('Unsigned 8-bit int')
        self.data_type_combo.addItem('Unsigned 16-bit int')
        self.data_type_combo.addItem('Unsigned 32-bit int')
        self.data_type_combo.currentIndexChanged.connect(self.updateStringView)
        right_pane.addWidget(self.data_type_combo)

        # Button to go back to original index
        self.reset_button = QPushButton('Go to Original Index')
        self.reset_button.clicked.connect(self.goToOriginalIndex)
        right_pane.addWidget(self.reset_button)

        # String view
        self.string_view = CustomTextEdit()
        self.string_view.setReadOnly(True)
        self.string_view.setFixedHeight(400)
        self.string_view.setFont(QFont('Consolas', 10))  # Monospace font
        self.string_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.string_view.setLineWrapMode(QPlainTextEdit.NoWrap)  # Disable line wrapping
        right_pane.addWidget(self.string_view)

        # Synchronize scrolling between hex_view and string_view
        self.hex_view.verticalScrollBar().valueChanged.connect(self.syncScrollBarsFromHex)
        self.string_view.verticalScrollBar().valueChanged.connect(self.syncScrollBarsFromString)

        # Synchronize selections between hex_view and string_view
        self.hex_view.selectionFinished.connect(self.onHexSelectionChanged)
        self.string_view.selectionFinished.connect(self.onStringSelectionChanged)

        # Load data into views
        self.loadHexView()
        self.updateStringView()

        # ==================== Bottom Pane Additions ====================

        # Separator (optional)
        separator = QLabel()
        separator.setFixedHeight(2)
        separator.setStyleSheet("background-color: #dcdcdc;")
        main_layout.addWidget(separator)

        # Bottom pane layout
        bottom_pane = QVBoxLayout()
        main_layout.addLayout(bottom_pane)

        # Controls Layout (Endianness Selector)
        controls_layout = QHBoxLayout()
        bottom_pane.addLayout(controls_layout)

        # Removed "Show Representations" Button as it's no longer needed
        # Endianness Selector
        self.endian_combo = QComboBox()
        self.endian_combo.addItem('Little Endian')
        self.endian_combo.addItem('Big Endian')
        controls_layout.addWidget(QLabel('Endianness:'))
        controls_layout.addWidget(self.endian_combo)

        # Connect endianness_combo to showRepresentations to recalculate on change
        self.endian_combo.currentIndexChanged.connect(self.showRepresentations)

        # Spacer to push controls to the left
        controls_layout.addStretch()

        # Representations Display
        self.representations_view = QPlainTextEdit()
        self.representations_view.setReadOnly(True)
        self.representations_view.setFont(QFont('Consolas', 10))  # Monospace font
        # Set size policy to prevent vertical expansion
        self.representations_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.representations_view.setLineWrapMode(QPlainTextEdit.NoWrap)  # Disable line wrapping
        bottom_pane.addWidget(self.representations_view)

    def calculateHexViewWidth(self):
        """
        Calculate the required fixed width for the hex_view based on font metrics
        and the number of bytes per line.
        """
        font = QFont('Consolas', 10)
        fm = self.hex_view.fontMetrics()
        # Each byte is represented as 'XX ' (3 characters), plus extra space every 4 bytes
        bytes_per_line = 16
        chars_per_byte = 3  # 'XX '
        extra_spaces = 2  # Extra space after every 4 bytes
        total_chars = bytes_per_line * chars_per_byte + (bytes_per_line // 4 - 1) * extra_spaces
        index_chars = 8 + 1 + 8 + 1  # Address + space + decimal index + colon
        # Estimate width based on average character width
        width = fm.width('X') * (total_chars + index_chars) + 20  # Additional padding
        return width

    def setupDecimalHeader(self):
        """
        Set up the decimal byte indices header without leading zeros.
        """
        decimal_header = "                   "  # Padding to align with address
        for i in range(16):
            decimal_header += f"{i:<2} "
            if (i + 1) % 4 == 0 and i != 15:
                decimal_header += "  "  # Extra space between 4-byte groups
        self.decimal_header.setText(decimal_header)

    def setupHexHeader(self):
        """
        Set up the hexadecimal byte indices header without leading zeros.
        """
        hex_header = "                   "  # Padding to align with address
        for i in range(16):
            hex_val = f"{i:02X}"
            hex_header += f"{hex_val} "
            if (i + 1) % 4 == 0 and i != 15:
                hex_header += "  "  # Extra space between 4-byte groups
        self.hex_header.setText(hex_header)

    def syncScrollBarsFromHex(self, value):
        if not self.syncing_scroll:
            self.syncing_scroll = True
            self.string_view.verticalScrollBar().setValue(value)
            self.syncing_scroll = False

    def syncScrollBarsFromString(self, value):
        if not self.syncing_scroll:
            self.syncing_scroll = True
            self.hex_view.verticalScrollBar().setValue(value)
            self.syncing_scroll = False

    def loadHexView(self):
        """
        Populate the hex_view with the hex representation of the data.
        """
        hex_str_list = []
        self.hex_positions = []
        pos = 0

        for line_index in range(0, len(self.data), 16):
            line_pos = pos
            line_bytes = self.data[line_index:line_index + 16]
            # Address with hexadecimal and decimal
            address = f"{line_index:08X} {('(' + str(line_index) + ')'):<7}: "
            hex_line = address
            pos += len(address)

            # Hex bytes
            byte_group = []
            for i, byte in enumerate(line_bytes):
                hex_byte = f"{byte:02X}"
                byte_group.append(hex_byte)
                self.hex_positions.append(pos)
                pos += len(hex_byte) + 1  # 'XX' + space
                # Add extra space after every 4 bytes except the last group
                if (i + 1) % 4 == 0 and i != 15:
                    byte_group.append(' ')  # Additional space between 4-byte groups
                    pos += 2
            # Pad the last line if it's not complete

            hex_line += ' '.join(byte_group)

            if len(line_bytes) < 16:
                hex_line += '   ' * (16 - len(line_bytes))  # 2 for hex and 1 for space
            
            hex_str_list.append(hex_line)
            pos = line_pos + len(hex_line) + 1  # For newline
        hex_str = '\n'.join(hex_str_list)
        self.hex_view.setPlainText(hex_str)

    def updateStringView(self):
        """
        Update the string_view based on the selected data type.
        Ensure that values are appropriately padded for alignment.
        """
        data_type = self.data_type_combo.currentText()
        string_lines = []
        pos = 0  # Position in the text
        self.string_byte_ranges = []

        # Define fixed width per data type for alignment
        data_type_width = {
            'ASCII': 1,  # Not used
            '8-bit int': 4,          # e.g., -128
            '16-bit int': 6,         # e.g., -32768
            '32-bit int': 11,        # e.g., -2147483648
            'Unsigned 8-bit int': 3, # e.g., 255
            'Unsigned 16-bit int': 5,# e.g., 65535
            'Unsigned 32-bit int': 10,# e.g., 4294967295
        }

        if data_type == 'ASCII':
            for line_index in range(0, len(self.data), 16):
                line_bytes = self.data[line_index:line_index + 16]
                line_chars = ''
                for i, b in enumerate(line_bytes):
                    ch = chr(b) if 32 <= b <= 126 else '.'
                    line_chars += ch
                    start_pos = pos
                    end_pos = pos + 1
                    byte_idx = line_index + i
                    self.string_byte_ranges.append((start_pos, end_pos, byte_idx, byte_idx + 1))
                    pos += 1
                # Pad the last line if it's not complete
                if len(line_bytes) < 16:
                    padding = ' ' * (16 - len(line_bytes))
                    line_chars += padding
                    pos += len(padding)
                string_lines.append(line_chars)
                pos += 1  # For newline
            string = '\n'.join(string_lines)
            self.string_view.setPlainText(string)
        else:
            fmt = ''
            size = 1
            if data_type == '8-bit int':
                fmt = 'b'
                size = 1
            elif data_type == '16-bit int':
                fmt = 'h'
                size = 2
            elif data_type == '32-bit int':
                fmt = 'i'
                size = 4
            elif data_type == 'Unsigned 8-bit int':
                fmt = 'B'
                size = 1
            elif data_type == 'Unsigned 16-bit int':
                fmt = 'H'
                size = 2
            elif data_type == 'Unsigned 32-bit int':
                fmt = 'I'
                size = 4
            else:
                self.string_view.setPlainText('')
                return

            pos = 0
            for line_index in range(0, len(self.data), 16):
                line_bytes = self.data[line_index:line_index + 16]
                values = []
                i = 0
                while i < len(line_bytes):
                    chunk = line_bytes[i:i + size]
                    if len(chunk) < size:
                        break
                    value = struct.unpack(fmt, chunk)[0]
                    value_str = str(value)

                    # Apply fixed width padding based on data type
                    fixed_width = data_type_width.get(data_type, len(value_str))
                    value_str_padded = f"{value_str:<{fixed_width}}"

                    values.append(value_str_padded)

                    # Calculate start and end positions for selection synchronization
                    start_pos = pos
                    end_pos = pos + len(value_str_padded)
                    byte_start_idx = line_index + i
                    byte_end_idx = byte_start_idx + size
                    self.string_byte_ranges.append((start_pos, end_pos, byte_start_idx, byte_end_idx))
                    pos += len(value_str_padded) + 1  # plus space
                    i += size
                # Pad the last line if it's not complete
                if i < 16:
                    remaining = 16 - i
                    # Calculate how many additional values to pad based on size
                    pad_values = remaining // size
                    for _ in range(pad_values):
                        fixed_width = data_type_width.get(data_type, 0)
                        if fixed_width > 0:
                            values.append(' ' * fixed_width)
                            pos += fixed_width + 1  # plus space
                line_str = ' '.join(values)
                string_lines.append(line_str)
                pos += 1  # For newline
            string = '\n'.join(string_lines)
            self.string_view.setPlainText(string)
        self.highlightIndex()

    def highlightIndex(self):
        """
        Highlight the specified byte/index in both hex_view and string_view.
        """
        # Clear previous formatting
        self.clearHighlights()

        # Highlight in hex_view
        byte_index = self.index
        if byte_index >= len(self.data):
            return  # Index out of range

        # Find line and position in line
        line_num = byte_index // 16
        byte_in_line = byte_index % 16

        # Calculate cursor position in hex_view
        if line_num >= self.hex_view.blockCount():
            return  # Line number out of range

        hex_cursor = self.hex_view.textCursor()
        block = self.hex_view.document().findBlockByNumber(line_num)
        hex_cursor.setPosition(block.position())
        # Move past address and ": "
        address = f"{(byte_index // 16) * 16:08X} {('(' + str((byte_index // 16) * 16) + ')'):<7}: "
        hex_cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, len(address))

        # Each byte is represented as 'XX' + ' ' (total 3 chars)
        # Additional space after every 4 bytes except the last group
        pos_in_line = byte_in_line * 3  # 'XX ' per byte
        pos_in_line += (byte_in_line // 4) * 2  # Extra space every 4 bytes

        hex_cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, pos_in_line)
        hex_cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 2)  # Highlight 'XX'

        # Apply highlight format
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('yellow'))
        hex_cursor.setCharFormat(fmt)
        self.hex_view.setTextCursor(hex_cursor)
        self.hex_view.ensureCursorVisible()

        # Highlight in string_view
        str_cursor = self.string_view.textCursor()
        block_num = byte_index // 16
        char_in_block = byte_index % 16

        if block_num >= self.string_view.blockCount():
            return  # Line number out of range

        str_cursor.setPosition(self.string_view.document().findBlockByNumber(block_num).position() + char_in_block)
        # Adjust for padding
        # Find the fixed width for the current data type
        data_type = self.data_type_combo.currentText()
        if data_type == 'ASCII':
            str_cursor.setPosition(str_cursor.position() + 1, QTextCursor.KeepAnchor)  # Highlight character
        else:
            # For non-ASCII, determine which value corresponds to the byte index
            # Iterate through string_byte_ranges to find the matching range
            for start_pos, end_pos, byte_start_idx, byte_end_idx in self.string_byte_ranges:
                if byte_start_idx <= byte_index < byte_end_idx:
                    str_cursor.setPosition(start_pos)
                    str_cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                    break
        # Apply highlight format
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('yellow'))
        str_cursor.setCharFormat(fmt)
        self.string_view.setTextCursor(str_cursor)
        self.string_view.ensureCursorVisible()

    def clearHighlights(self):
        """
        Clear all highlights in hex_view and string_view.
        """
        # Clear hex_view highlights
        hex_cursor = self.hex_view.textCursor()
        hex_cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#3c3f41'))  # Reset to background color
        hex_cursor.setCharFormat(fmt)
        self.hex_view.setTextCursor(hex_cursor)

        # Clear string_view highlights
        str_cursor = self.string_view.textCursor()
        str_cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#3c3f41'))  # Reset to background color
        str_cursor.setCharFormat(fmt)
        self.string_view.setTextCursor(str_cursor)

    def goToOriginalIndex(self):
        """
        Navigate back to the originally specified index.
        """
        self.index = self.original_index
        self.highlightIndex()

    def showRepresentations(self):
        """
        Show all representations for the selected bytes in the bottom pane.
        """
        selected_text = self.hex_view.textCursor().selectedText()
        if not selected_text:
            self.representations_view.setPlainText("No bytes selected.")
            return

        # Clean the selected text by removing spaces and any non-hex characters
        clean_hex = ''.join(filter(str.isalnum, selected_text))
        if len(clean_hex) % 2 != 0:
            self.representations_view.setPlainText("Invalid selection. Please select whole bytes.")
            return

        try:
            byte_values = bytes.fromhex(clean_hex)
        except ValueError:
            self.representations_view.setPlainText("Invalid hex selection.")
            return

        endian = self.endian_combo.currentText()
        endian_char = '<' if endian == 'Little Endian' else '>'

        representations = []

        # Hex Representation
        hex_rep = ' '.join(f"{b:02X}" for b in byte_values)
        representations.append(f"Hex: {hex_rep}")

        # ASCII Representation
        try:
            ascii_rep = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in byte_values)
            representations.append(f"ASCII: {ascii_rep}")
        except:
            representations.append("ASCII: [Invalid]")

        # Signed Integers
        if len(byte_values) >= 1:
            val = struct.unpack(endian_char + 'b', byte_values[:1])[0]
            val_hex = '0x' + byte_values[0:1].hex().upper()
            representations.append(f"Signed 8-bit Int: {val} ({val_hex})")
            val_u = struct.unpack(endian_char + 'B', byte_values[:1])[0]
            representations.append(f"Unsigned 8-bit Int: {val_u} ({val_hex})")
        if len(byte_values) >= 2:
            val = struct.unpack(endian_char + 'h', byte_values[:2])[0]
            val_hex = '0x' + byte_values[0:2].hex().upper()
            representations.append(f"Signed 16-bit Int: {val} ({val_hex})")
            val_u = struct.unpack(endian_char + 'H', byte_values[:2])[0]
            representations.append(f"Unsigned 16-bit Int: {val_u} ({val_hex})")
        if len(byte_values) >= 4:
            val = struct.unpack(endian_char + 'i', byte_values[:4])[0]
            val_hex = '0x' + byte_values[0:4].hex().upper()
            representations.append(f"Signed 32-bit Int: {val} ({val_hex})")
            val_u = struct.unpack(endian_char + 'I', byte_values[:4])[0]
            representations.append(f"Unsigned 32-bit Int: {val_u} ({val_hex})")

        # Floating Point (if 4 or 8 bytes)
        if len(byte_values) >= 4:
            try:
                val = struct.unpack(endian_char + 'f', byte_values[:4])[0]
                val_hex = '0x' + byte_values[0:4].hex().upper()
                representations.append(f"Float (32-bit): {val} ({val_hex})")
            except:
                representations.append("Float (32-bit): [Invalid]")
        if len(byte_values) >= 8:
            try:
                val = struct.unpack(endian_char + 'd', byte_values[:8])[0]
                val_hex = '0x' + byte_values[0:8].hex().upper()
                representations.append(f"Double (64-bit): {val} ({val_hex})")
            except:
                representations.append("Double (64-bit): [Invalid]")

        # Join all representations
        rep_text = '\n'.join(representations)
        self.representations_view.setPlainText(rep_text)

    # ==================== Selection Synchronization Methods ====================

    def onHexSelectionChanged(self):
        """
        Handle selection changes in the hex_view and apply corresponding selection in string_view.
        """
        if self.syncing_selection:
            return  # Prevent recursive calls

        self.syncing_selection = True

        # Get selected byte indices in hex_view
        byte_indices = self.getSelectedBytesHex()
        # print(byte_indices)

        if byte_indices:
            # Apply selection in string_view
            self.applySelectionToStringView(byte_indices[0], byte_indices[-1])
            # Automatically show representations
            self.showRepresentations()
        else:
            # Clear selection in string_view
            self.clearStringViewSelection()
            self.representations_view.setPlainText("")

        self.syncing_selection = False

    def onStringSelectionChanged(self):
        """
        Handle selection changes in the string_view and apply corresponding selection in hex_view.
        """
        if self.syncing_selection:
            return  # Prevent recursive calls

        self.syncing_selection = True

        # Get selected byte indices in string_view
        byte_indices = self.getSelectedBytesString()

        if byte_indices:
            # Apply selection in hex_view
            self.applySelectionToHexView(byte_indices[0], byte_indices[-1])
            # Automatically show representations
            self.showRepresentations()
        else:
            # Clear selection in hex_view
            self.clearHexViewSelection()
            self.representations_view.setPlainText("")

        self.syncing_selection = False

    def getSelectedBytesHex(self):
        """
        Get the list of byte indices selected in hex_view.
        """
        cursor = self.hex_view.textCursor()
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()

        selected_bytes = []
        for byte_idx, pos in enumerate(self.hex_positions):
            byte_start = pos
            byte_end = pos + 2  # Each byte is represented by two hex characters
            # Check if the byte overlaps with the selection
            if byte_end < selection_start or byte_start > selection_end:
                continue
            # If any part of the byte is within the selection
            if (byte_start <= selection_start < byte_end) or \
               (byte_start < selection_end <= byte_end) or \
               (selection_start <= byte_start and selection_end >= byte_end):
                selected_bytes.append(byte_idx)
        return selected_bytes

    def getSelectedBytesString(self):
        """
        Get the list of byte indices selected in string_view.
        """
        cursor = self.string_view.textCursor()
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()

        if selection_start == selection_end:
            return []

        selected_byte_indices = set()
        for start_pos, end_pos, byte_start_idx, byte_end_idx in self.string_byte_ranges:
            # If the value overlaps with the selection
            if end_pos <= selection_start or start_pos >= selection_end:
                continue
            # The value is within the selection
            selected_byte_indices.update(range(byte_start_idx, byte_end_idx))
        selected_byte_indices = sorted(selected_byte_indices)
        return selected_byte_indices

    def positionToByteIndexString(self, pos):
        """
        Convert a cursor position in string_view to a list of byte indices.
        """
        byte_indices = []
        for start_pos, end_pos, byte_start_idx, byte_end_idx in self.string_byte_ranges:
            if start_pos <= pos < end_pos:
                return byte_start_idx, byte_end_idx
        return None

    def applySelectionToStringView(self, byte_start, byte_end):
        """
        Apply selection in string_view based on byte indices.
        """
        # Find the positions corresponding to the byte indices
        start_positions = []
        end_positions = []
        for start_pos, end_pos, byte_start_idx, byte_end_idx in self.string_byte_ranges:
            # If the value overlaps with the byte range
            if byte_end <= byte_start_idx or byte_start >= byte_end_idx:
                continue
            # The value is within the byte range
            start_positions.append(start_pos)
            end_positions.append(end_pos)
        if not start_positions or not end_positions:
            return  # No positions found
        selection_start = min(start_positions)
        selection_end = max(end_positions)
        cursor = self.string_view.textCursor()
        cursor.setPosition(selection_start)
        cursor.setPosition(selection_end + 1, QTextCursor.KeepAnchor)
        self.string_view.setTextCursor(cursor)

    def applySelectionToHexView(self, byte_start, byte_end):
        """
        Apply selection in hex_view based on byte indices.
        """
        if byte_start >= len(self.hex_positions) or byte_end >= len(self.hex_positions):
            return

        start_pos = self.hex_positions[byte_start]
        end_pos = self.hex_positions[byte_end] + 2  # Each byte is two characters

        cursor = self.hex_view.textCursor()
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
        self.hex_view.setTextCursor(cursor)

    def clearStringViewSelection(self):
        """
        Clear selection in string_view.
        """
        cursor = self.string_view.textCursor()
        cursor.clearSelection()
        self.string_view.setTextCursor(cursor)

    def clearHexViewSelection(self):
        """
        Clear selection in hex_view.
        """
        cursor = self.hex_view.textCursor()
        cursor.clearSelection()
        self.hex_view.setTextCursor(cursor)


# ----------------------- Entry Point -----------------------

if __name__ == '__main__':
    if os.path.exists(args.file_path):
        with open(args.file_path, 'rb') as f:
            data = f.read()

        app = QApplication(sys.argv)
        window = MainWindow(data, args.index)
        window.show()
        sys.exit(app.exec_())
