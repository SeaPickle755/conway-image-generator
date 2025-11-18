import re
from typing import List, Tuple, Dict
from PIL import Image # NEW: Added for image processing
import sys
# Define the grid representation: 'o' for alive, '.' for dead.

# --- RLE UTILITY FUNCTIONS (Original Code Kept) ---

def parse_rle_header(rle_string: str) -> Tuple[Dict[str, str], str]:
    """
    Parses the header (x, y, rule) and the RLE data string from the full input.
    """
    # 1. Strip the comment/metadata section (up to the 'x = ...' line)
    data_start = re.search(r'x\s*=\s*\d+', rle_string)
    if not data_start:
        raise ValueError("RLE file is missing the 'x = ...' header line.")

    header_line_match = re.search(r'(x\s*=\s*\d+,\s*y\s*=\s*\d+,\s*rule\s*=\s*[bB]\d*/[sS]\d+)', rle_string, re.IGNORECASE)

    if not header_line_match:
        # Fallback for simpler files that might not have the full header on one line
        header_line_match = re.search(r'(x\s*=\s*\d+).*?(y\s*=\s*\d+).*?(rule\s*=\s*[bB]\d*/[sS]\d+)', rle_string, re.IGNORECASE | re.DOTALL)
        if not header_line_match:
            raise ValueError("Could not find a valid RLE header line.")
        
        # Reconstruct header text from groups
        header_text = f"{header_line_match.group(1)}, {header_line_match.group(2)}, {header_line_match.group(3)}"
        rle_data_start_index = header_line_match.end()
    else:
        header_text = header_line_match.group(1)
        # The pattern data starts immediately after the rule definition
        rle_data_start_index = header_line_match.end()
        
    rle_data = rle_string[rle_data_start_index:].strip()

    # 2. Parse the header line into a dictionary
    header = {}
    parts = [p.strip() for p in header_text.split(',')]
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            header[key.strip()] = value.strip()

    return header, rle_data


def decode_rle_data(rle_data: str, width: int, height: int) -> List[List[str]]:
    """Decodes the RLE pattern data into a 2D grid."""
    grid = [['.' for _ in range(width)] for _ in range(height)]
    row, col = 0, 0
    run_count = 0

    cleaned_data = rle_data.rstrip('!').replace('$', ' $ ')
    tokens = re.findall(r'\d+|[bo$]', cleaned_data)

    for token in tokens:
        if token.isdigit():
            run_count = int(token)
        elif token in ('o', 'b'):
            count = run_count if run_count > 0 else 1
            cell_type = 'o' if token == 'o' else '.'

            for _ in range(count):
                if row < height and col < width:
                    grid[row][col] = cell_type
                    col += 1
            run_count = 0
        elif token == '$':
            count = run_count if run_count > 0 else 1
            row += count
            col = 0
            run_count = 0

    return grid


def encode_rle(grid: List[List[str]]) -> str:
    """Encodes a 2D grid back into the RLE pattern data string."""
    rle_lines = []

    def get_rle_char(cell):
        return 'o' if cell == 'o' else 'b'

    for i, row in enumerate(grid):
        rle_row = ""
        rle_chars = [get_rle_char(cell) for cell in row]

        while rle_chars and rle_chars[-1] == 'b':
            rle_chars.pop()

        if not rle_chars:
            rle_lines.append('')
            continue

        current_char = rle_chars[0]
        count = 0
        for char in rle_chars:
            if char == current_char:
                count += 1
            else:
                rle_row += (str(count) if count > 1 else "") + current_char
                current_char = char
                count = 1

        rle_row += (str(count) if count > 1 else "") + current_char
        rle_lines.append(rle_row)

    final_rle_data = ""
    empty_row_count = 0

    for line in rle_lines:
        if line == '':
            empty_row_count += 1
        else:
            if empty_row_count > 0:
                final_rle_data += (str(empty_row_count) if empty_row_count > 1 else "") + '$'
            
            final_rle_data += line + '$'
            empty_row_count = 0

    return final_rle_data.rstrip('$') + '!'


def tile_grid(base_grid: List[List[str]], repeat_x: int, repeat_y: int) -> List[List[str]]:
    """Tiles the base grid across a new larger grid."""
    if not base_grid or not base_grid[0]:
        return []
        
    base_height = len(base_grid)
    base_width = len(base_grid[0])
    
    new_height = base_height * repeat_y
    new_width = base_width * repeat_x
    
    new_grid = [['.' for _ in range(new_width)] for _ in range(new_height)]
    
    for ty in range(repeat_y):
        for tx in range(repeat_x):
            start_row = ty * base_height
            start_col = tx * base_width
            
            for r in range(base_height):
                for c in range(base_width):
                    new_row = start_row + r
                    new_col = start_col + c
                    new_grid[new_row][new_col] = base_grid[r][c]
                        
    return new_grid


# --- IMAGE PROCESSING AND GLIDER TILING FUNCTIONS (NEW/MODIFIED) ---

def image_to_pixel_map(image_path: str, threshold: int = 128) -> List[List[str]]:
    """
    Converts an image into a 2D grid ('o' for bright, '.' for dark) based on a brightness threshold.

    Args:
        image_path: Path to the input image file.
        threshold: Grayscale value (0-255) above which a pixel is considered 'bright' ('o').
                   128 is a typical middle ground.

    Returns:
        A 2D list representing the low-resolution pixel map.
    """
    try:
        # Open the image and convert it directly to grayscale ('L' mode)
        img = Image.open(image_path).convert('L')
    except FileNotFoundError:
        print(f"Error: Image file not found at '{image_path}'.")
        return []
    except ImportError:
        print("Error: Pillow library not installed. Please run 'pip install Pillow'.")
        return []

    width, height = img.size
    pixel_map = []
    
    # Iterate through rows (y) and columns (x)
    for y in range(height):
        row = []
        for x in range(width):
            # Get the grayscale brightness value (0=Black, 255=White)
            brightness = img.getpixel((x, y)) 
            
            # Bright pixel gets an 'o' (will be replaced by a Glider later)
            if brightness > threshold:
                row.append('o')
            # Dark pixel gets a '.' (will be left empty)
            else:
                row.append('.')
        pixel_map.append(row)
        
    return pixel_map


def create_pixel_art_grid(
    pixel_art_map: List[List[str]],
    base_pattern: List[List[str]]
) -> List[List[str]]:
    """
    Creates a large grid by tiling a base pattern only where the 
    pixel_art_map indicates an 'alive' cell ('o'). (Reused from previous turn).
    """
    if not base_pattern or not base_pattern[0] or not pixel_art_map:
        return []
        
    base_height = len(base_pattern)
    base_width = len(base_pattern[0])
    map_height = len(pixel_art_map)
    map_width = len(pixel_art_map[0])
    
    new_height = map_height * base_height
    new_width = map_width * base_width
    
    new_grid = [['.' for _ in range(new_width)] for _ in range(new_height)]
    
    for map_r in range(map_height):
        for map_c in range(map_width):
            if pixel_art_map[map_r][map_c] == 'o':
                start_row = map_r * base_height
                start_col = map_c * base_width
                
                # Copy the base pattern into the tile area
                for r in range(base_height):
                    for c in range(base_width):
                        new_row = start_row + r
                        new_col = start_col + c
                        # Only copy the alive cells from the base pattern
                        if base_pattern[r][c] == 'o':
                            new_grid[new_row][new_col] = 'o'
                            
    return new_grid


# --- CONFIGURATION AND DEMONSTRATION ---

# Define the Glider pattern (our new 'pixel' base)
GLIDER_GRID = [
    ['.','.','.', '.', '.', '.', '.'],
    ['.','.','.', 'o', '.', '.', '.'],
    ['.','.','o', '.', '.', '.', '.'],
    ['.','.','o', 'o', 'o', '.', '.'],
    ['.','.','.', '.', '.', '.', '.'],
]

# --- USER CONFIGURATION ---
IMAGE_PATH = sys.argv[1] # <-- !!! CHANGE THIS TO YOUR IMAGE FILE PATH !!!
BRIGHTNESS_THRESHOLD = int(sys.argv[2])     # Pixels brighter than this (0-255) get a Glider.
GAME_OF_LIFE_RULE = 'B3/S23'   # Standard Conway's Game of Life rule
# -------------------------


print("--- 1. Generating Pixel Map from Image ---")
try:
    # 1. Convert the image file to a low-res pixel map
    pixel_map = image_to_pixel_map(IMAGE_PATH, BRIGHTNESS_THRESHOLD)

    if not pixel_map:
        raise ValueError("Image processing failed or pixel map is empty.")
        
    map_width = len(pixel_map[0])
    map_height = len(pixel_map)

    print(f"Image successfully converted to {map_width}x{map_height} pixel map.")
    print("Example rows from the Pixel Map ('o' = Glider, '.' = Empty):")
    for row in pixel_map[:5]:
        print("".join(row))
    if map_height > 5:
        print("...")

    print("\n" + "="*50 + "\n")

    print("--- 2. Tiling Gliders to Create Final RLE Grid ---")

    # 2. Use the pixel map to tile the Glider pattern
    final_glider_art_grid = create_pixel_art_grid(pixel_map, GLIDER_GRID)
    
    # 3. Calculate final RLE dimensions
    glider_width = len(GLIDER_GRID[0])
    glider_height = len(GLIDER_GRID)
    final_width = map_width * glider_width
    final_height = map_height * glider_height
    
    # 4. Encode the new grid
    final_rle_data = encode_rle(final_glider_art_grid)

    # 5. Create the final RLE file content with the new header
    full_final_rle_output = f"x = {final_width}, y = {final_height}, rule = {GAME_OF_LIFE_RULE}\n{final_rle_data}"

    print(f"Generated Glider Art Grid size: {final_width}x{final_height}")
    print(f"Generated RLE Output (first 300 characters):")
    print(full_final_rle_output[:300] + ('...' if len(full_final_rle_output) > 300 else ''))
    print(f"\nTotal length of RLE string: {len(final_rle_data)}")
    print("\n--- RLE Data Ready for Game of Life Simulator ---\n")
    # Output the full RLE data for easy copying/saving
    # print(full_final_rle_output)
    with open("RLE.txt", "w") as f:
        f.write(full_final_rle_output)
    print("Wrote RLE to RLE.txt")


except ValueError as e:
    print(f"Error in Glider Art Generation: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
