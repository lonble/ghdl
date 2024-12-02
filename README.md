# ghdl

A config file based python script to download the latest release assets from github.

## Installation

Just clone the repository or download the `.py` file.

## Usage

```sh
python3 ghdl.py -c config.json
```

You can adjust the logging level with the `-l` parameter.

```sh
python3 ghdl.py -c config.json -l info
```

Use the `-h` parameter to see detailed usage.

## Configuration

ghdl uses **json** as the configuration format, and there is an example configuration file named `config.json` in the repository.

The explanation of each field in the configuration is as follows:

- `overwrite`: Whether to overwrite the file if it already exists. **Default**: `true`
- `clear_matches`: Whether to delete files in the download directory that match the filters before downloading. **Default**: `false`
- `dir`: Download directory. **Default**: `""`, which means the current working directory
- `token`: Global GitHub token. **Default**: `""`, which means that the token will not be used
- `concurrency`: Number of concurrency. Setting it to `0` instead of `1` to disable concurrency. **Default**: `5`
- `repos`: List of repository configurations. **This field is required**, but can be empty
- `owner`: Owner of the repository. **This field is required**
- `repo`: Repository name. **This field is required**
- `token` in `repos`: Repository specified token. If it is empty then global token will be used. **Default**: `""`
- `filters`: List of filters. Only matched files will be downloaded. Each filter is a **regular expression** that requires a full match of the filename, `""` means nothing matches. An empty list means all matches. **Default**: `[]`
