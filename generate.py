import yaml
import json
import os
import re
import shutil
import base64
import io
import time
import requests
from jsonschema import validate, ValidationError
from PIL import Image


BOARD_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': { 'type': 'string' },
        'chip': { 'type': 'string' },
        'cores': { 'type': 'string' },
        'flash': { 'type': 'string', 'pattern': '^(\\d+\\s*(KB|MB|GB)|0)$' },
        'ram': { 'type': 'string', 'pattern': '^\\d+\\s*(KB|MB|GB)$' },
        'usb': { 'type': 'string', 'enum': [ 'micro', 'type-c' ] },
        'dimensions': { 'type': 'string' },
        'connectivity': {
            'type': 'array',
            'items': { 'type': 'string', 'enum': [ 'WiFi', 'BLE', 'Lora', 'Zigbee', 'Ethernet' ] }
        },
        'connectors': {
            'type': 'array',
            'items': { 'type': 'string', 'enum': [ 'Qwiic', 'SP/CE', 'PiDebug', 'BConnect', 'CSI', 'microSD', 'RJ45', 'RTC', 'LiPo-PH2.0', 'LiPo-MX1.25', 'CAN' ] }
        },
        'smd': { 'type': 'boolean' },
        'notes': {'type': [ 'string', 'null' ] },
        'image': { 'type': [ 'string', 'null' ], 'format': 'uri' },
        'url': { 'type': [ 'string', 'null' ], 'format': 'uri' }
    },
    'required': [ 'name', 'chip', 'cores', 'flash', 'ram', 'usb', 'dimensions', 'smd', 'image', 'url' ],
    'additionalProperties': False
}


def parse_memory_size(size_str):
    if not size_str or size_str == '0':
        return 0

    match = re.match(r'(\d+)\s*(KB|MB|GB)', size_str.upper())
    if not match:
        raise ValueError(f'Error: Invalid memory size format: "{size_str}"!')

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 'KB':
        return value * 1024

    if unit == 'MB':
        return value * 1024 * 1024

    if unit == 'GB':
        return value * 1024 * 1024 * 1024

    return 0


def generate_thumbnail(image_url, max_size=(64, 64), quality=85):
    if not image_url:
        return None

    try:
        print('\tFetching image... ', end='\r')

        req = requests.get(image_url, stream=True, timeout=10)

        total_size = int(req.headers.get('content-length', 0))
        downloaded = 0
        image_data = bytearray()

        with req as r:
            r.raise_for_status()
            for chunk in r.iter_content(1024):
                downloaded += len(chunk)
                image_data.extend(chunk)
                print(f'\tFetching image... {downloaded / total_size:.0%}', end='\r')
        print('', end='\r')

        with Image.open(io.BytesIO(image_data)) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))

                if img.mode == 'P':
                    img = img.convert('RGBA')

                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                    img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            buffer.seek(0)

            return 'data:image/jpeg;base64,' + base64.b64encode(buffer.read()).decode('utf-8')
    except Exception as e:
        print(f'\tError generating thumbnail: {e}')
        return None


def main():
    boards_dir = 'boards'
    template_dir = 'page_template'
    output_dir = 'out'

    if not os.path.exists(boards_dir):
        print(f'Error: Directory "{boards_dir}" not found!')
        exit(1)

    if not os.path.exists(template_dir):
        print(f'Error: Directory "{template_dir}" not found!')
        exit(1)

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    all_data = []
    data_valid = True

    files = os.listdir(boards_dir)
    files.sort()

    for filename in files:
        if not filename.endswith('.yaml') or filename == '_template.yaml':
            continue

        print(f'Processing "{filename}"...')

        filepath = os.path.join(boards_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                board_data = yaml.safe_load(f)

            validate(instance=board_data, schema=BOARD_SCHEMA)

            board_data['flash_bytes'] = parse_memory_size(board_data.get('flash'))
            board_data['ram_bytes'] = parse_memory_size(board_data.get('ram'))

            board_data.setdefault('connectivity', [])
            board_data.setdefault('connectors', [])
            board_data.setdefault('notes', '')
            board_data.setdefault('thumbnail', None)

            if board_data.get('image'):
                board_data['thumbnail'] = None
                for _ in range(3):
                    board_data['thumbnail'] = generate_thumbnail(board_data['image'])
                    if board_data['thumbnail']:
                        break

                    time.sleep(5)

                if board_data['thumbnail'] is None:
                    data_valid = False
                    break

            all_data.append(board_data)

        except yaml.YAMLError as e:
            print(f'\tError parsing YAML: {e}')
            data_valid = False
        except ValidationError as e:
            print(f'\tError validating schema: {e.message}:')
            data_valid = False
        except ValueError as e:
            print(f'\tValue error: {e}')
            data_valid = False
        except Exception as e:
            print(f'\tUnexpected error: {e}')
            data_valid = False

    if not data_valid:
        print('\nErrors found during processing. Aborting!')
        exit(1)

    json_path = os.path.join(output_dir, 'board_data.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'data': all_data}, f, indent=2)
    print(f'Successfully wrote {len(all_data)} boards to "{json_path}"!')

    for item in os.listdir(template_dir):
        src = os.path.join(template_dir, item)
        dest = os.path.join(output_dir, item)

        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)


if __name__ == '__main__':
    main()
