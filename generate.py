import yaml
import json
import os
import re
import shutil
from jsonschema import validate, ValidationError


BOARD_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': { 'type': 'string' },
        'chip': { 'type': 'string' },
        'flash': { 'type': 'string', 'pattern': '^\\d+\\s*(KB|MB|GB)$' },
        'ram': { 'type': 'string', 'pattern': '^\\d+\\s*(KB|MB|GB)$' },
        'usb': { 'type': 'string', 'enum': [ 'micro', 'type-c' ] },
        'connectivity': {
            'type': 'array',
            'items': { 'type': 'string', 'enum': [ 'wifi', 'ble', 'lora', 'zigbee', 'ethernet' ] }
        },
        'smd': { 'type': 'boolean' },
        'image': { 'type': [ 'string', 'null' ], 'format': 'uri' },
        'url': { 'type': [ 'string', 'null' ], 'format': 'uri' },
        'notes': {'type': [ 'string', 'null' ] }
    },
    'required': [ 'name', 'chip', 'flash', 'ram', 'usb', 'smd', 'image', 'url' ],
    'additionalProperties': False
}


def parse_memory_size(size_str):
    if not size_str:
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

    for filename in os.listdir(boards_dir):
        if not filename.endswith('.yaml') or filename == '_template.yaml':
            continue

        print(f'Processing "{filename}" ...')

        filepath = os.path.join(boards_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                board_data = yaml.safe_load(f)

            validate(instance=board_data, schema=BOARD_SCHEMA)

            board_data['flash_bytes'] = parse_memory_size(board_data.get('flash'))
            board_data['ram_bytes'] = parse_memory_size(board_data.get('ram'))

            board_data.setdefault('connectivity', [])
            board_data.setdefault('notes', '')

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
    print(f'\nSuccessfully wrote {len(all_data)} boards to "{json_path}"!')

    for item in os.listdir(template_dir):
        src = os.path.join(template_dir, item)
        dest = os.path.join(output_dir, item)

        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)


if __name__ == '__main__':
    main()
