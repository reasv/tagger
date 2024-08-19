# Panoptikon

## State of the art, local, multimodal, multimedia search engine
Panoptikon indexes your local files using state-of-the-art AI and Machine learning models and makes difficult-to-search media such as images and videos easily findable.

Combining OCR, Whisper Speech To Text, CLIP Image Embeddings, Text Embeddings, Full Text Search, Automated Tagging, Automated Image Captioning, Panoptikon is the swiss army knife of local media indexing. 

Panoptikon aims to be the `text-generation-webui` or `stable-diffusion-webui` for search.
It is fully customizable, and allows you to easily configure custom models for any of the supported tasks. It comes with a wealth of capable models available out of the box, but adding another model or a newer finetune is never more than a few TOML configuration lines away.
As long as a model is supported by any of the built-in implementation classes (Among other things, supporting OpenCLIP, Sentence Transformers, Faster Whisper) you can simply add the huggingface repo for your custom model to the inference server configuration, and it will immediately be available for use.

Panoptikon is designed to keep the index data from multiple models (or different configurations of the same model) **side by side**, letting you choose which one(s) to use *at search time*. As such, Panoptikon is an excellent tool for the purpose of comparing the real-world performance of different methods of data extraction or embedding models, also allowing you to leverage their combined power instead of only relying on one. For example, when searching for a tag, you can configure a list of tagging models to use, and choose whether to match an item if at least one model has set the tags you're searching for, or whether to require that all of them have.

The intended use of Panoptikon is for power users and more technically minded enthusiasts to leverage more powerful or custom open source models to index and search their files.
Unlike tools such as Hydrus, Panoptikon will never copy, move or otherwise touch your files. Simply add your directories to the list of allowed paths, and run the indexing jobs.
Panoptikon will build an index inside its own SQLite database, referencing the original source file paths. Files are kept track of by their hash, so there's no issue with renaming or moving them, so long as they remain within one of the directory trees Panoptikon has access to, and so long as you run the File Scan job regularly, or enable the scheduled cronjob.

### Warning
Panoptikon is designed as a local service and is not intended to be exposed to the internet. It does not currently have any security features, and currently exposes, among other things, an API to access *all* your files, even outside of explicitly indexed directories. Panoptikon binds to localhost by default, and if you intend to expose it, you should add a reverse proxy with authentication such as HTTP Basic Auth or OAuth2 in front of it.
In the future, Panoptikon will feature a more secure API, authentication, and a React-based client that can be publicly exposed.

## Installation
```
poetry install --with inference
```
To install the full system including the inference server dependencies.
If you're running the inference server on a different machine, you can omit the `--with inference` flag, and set the `INFERENCE_API_URL` environment variable to point to the URL of the inference server (see below).
### CUDA on Windows
If you're on windows and want CUDA GPU acceleration, you have to uninstall the default pytorch and install the correct version after running `poetry install`:
```
pip3 uninstall torch torchvision torchaudio
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```
You may have to repeat this after updates.
### Other dependency issues
#### cuDNN
When running the Whisper implementation, which is based on [CTranslate2](https://github.com/OpenNMT/CTranslate2/), you may see errors related to cuDNN libraries.
Download a cuDNN version 8.x appropriate for your system from [Nvidia](https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/), unpack the archive and save its contents inside the `cudnn` directory at the root of this repo.
Make sure the cudnn folder contains `bin`, `lib`, `include`, etc as direct subfolders.

#### Weasyprint
This is only relevant if you intend to use Panoptikon with HTML files.
Panoptikon uses [Weasyprint](https://doc.courtbouillon.org/weasyprint/stable/index.html) to handle HTML files. You have to follow their [Installation Guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) in order to ensure all the external dependencies are present on your system. If they are present but not found, it's recommended to set the `WEASYPRINT_DLL_DIRECTORIES` environment variable to point to the correct folder.

## Running Panoptikon
```
poetry run panoptikon
```
Will start panoptikon along with its inference server, listening by default at http://127.0.0.1:6342/

Everything except for adding and customizing the AI models used can be done through the gradio UI available at `/gradio`

## First steps
Open http://127.0.0.1:6342/gradio and start by adding the directories you want to index, one path per line, in the `Include Directories` field. If you want to exclude some subdirectories, these go in the `Exclude Directories` field.
After setting the directories, Click on `Update Directory Lists and Scan New Entries`.
This will run a job to hash and index all files of eligible file types.
Whenever there are file changes you should run `Rescan All Directories` or set up the regular cronjob as explained in the UI in order to have this done automatically.

After the basic indexing is done, you can run any of the models, which are all available on the same page, in order to generate searchable data from your files. This will initiate a data extraction job.
After the job is finished, you search your files from the `search` tab.

## Search
The `Search` tab features Panoptikon's search functionality. Search criteria are divided in tabs, and note that by default most tabs will be hidden, because you haven't yet produced the relevant data using the various models. For example, Semantic Search will only be visible if you've either generated CLIP or Text embeddings.

## Bookmarks
You can bookmark any search result. Simply type in a group name for the bookmarks group it should be saved under (or leave it as the default "default" and click on "Bookmark").
The same item can belong to any number of bookmark groups, and bookmark groups can have arbitrary names.

You can check out your bookmarks from the `Bookmarks` tab.
You can also search inside your bookmarks using the regular search UI, by checking `Restrict Search to bookmarked Items` on the search page.

Without any other search criteria, this is effectively just another way to browse your bookmarks, but it's a lot more flexible since you can use any of the regular search criteria along with being able to optionally select which specific groups to include.

## Adding more models
See `config/inference/example.toml` for examples on how to add custom models from Hugging Face to Panoptikon.

## Environment variables and config
Aside from the inference config, which uses TOML, and the configuration saved in the SQLite database, which can be modified through the UI, Panoptikon accepts environment variables as config options.
Panoptikon uses dotenv, so you can create a file called `.env` in this directory with all the environment variables and their values and it will be automatically applied at runtime.

### HOST and PORT
Default:
```
HOST="127.0.0.1"
PORT="6342"
```
These determine where to bind the Panoptikon server which delivers both the inference API and the search and configuration UI.
Warning: Do not expose Panoptikon to the internet without a reverse proxy and authentication. It is designed as a local service and does not have any security features.

### INFERIO_HOST, INFERIO_PORT
Default
```
INFERIO_HOST="127.0.0.1"
INFERIO_PORT="7777"
```
These **ONLY** apply when the inference server (inferio) is run separately as standalone without Panoptikon.
These determine where to bind the inference server which runs the models.
To run the inference server separately, you can run `poetry run inferio`.
### INFERENCE_API_URL
Default: Not set.

If you're running the inference server separately, you can point this to the URL of the inference server to allow Panoptikon to use it.

By default, a Panoptikon instance will run its own inference server, which also means that you can point INFERENCE_API_URL to another Panoptikon instance to leverage its inference server.
For example, you might have a full Panoptikon instance running on your desktop or workstation, and another instance running on your laptop without a GPU, and you can point the laptop instance to the desktop instance's inference server to leverage the GPU.
Simply configure the desktop instance to run the inference server on an IP reachable from the laptop, and set INFERENCE_API_URL to the URL of the desktop instance's inference server, for example `http://192.168.1.16:6342`. Don't add a trailing slash.

### DATA_FOLDER
Default:
```
DATA_FOLDER="data"
```
Where to store the databases and logs. Defaults to "data" inside the current directory.
### LOGLEVEL
Default
```
LOGLEVEL="INFO"
```
The loglevel for the logger. You can find the log files under `[DATA_FOLDER]/logs`

### INDEX_DB, USER_DATA_DB, STORAGE_DB

Default:
```
INDEX_DB="default"
STORAGE_DB=[Automatically set to the same value as INDEX_DB]
USER_DATA_DB="default"
```
These are the names of the SQLite databases used by Panoptikon. You can set them to different values to have multiple independent Panoptikon instances running on the same machine, or to have different dataesets or configurations.
The actual databases are stored under `[DATA_FOLDER]`.

INDEX_DB is used to store the index data, such as file hashes and paths, and the extracted data from the models, as well as the related configuration such as which paths to index, excluded paths, cronjob settings, rule settings, etc.
STORAGE_DB is used to store thumbnails. If you set INDEX_DB to a different value, STORAGE_DB will be set to the same value by default, so there is no need to manually specify a different name for STORAGE_DB.

The USER_DATA_DB is used to store user-specific data such as bookmarks. You can use the same USER_DATA_DB for multiple INDEX_DBs if you want to share bookmarks between them. In fact, this is what you're intended to do. There's no need to have separate sets of bookmarks for different datasets. Keep a single USER_DATA_DB and set INDEX_DB to different values to separate your indexed files.
However, only bookmarks related to files that are indexed in the current INDEX_DB will be shown in the UI. If a file is bookmarked and not present in the current INDEX_DB, it will not be shown in the bookmarks tab, nor will it be findable by search but it's still present in the USER_DATA_DB, so if you switch back to the INDEX_DB where the file is indexed, you will see the bookmark again.
Bookmarks are by hash, not by path, so if the same file is indexed in multiple INDEX_DBs, it will have the same bookmark in all of them.

You should not run multiple Panoptikon instances with the same INDEX_DB at the same time, as they will try to write to the same database file and will simply fail.
The USER_DATA_DB can be shared between two running Panoptikon instances, but if you were setting a bookmark on both at the same time, as unlikely as that is, one of the two actions would error out.

### TEMP_DIR
```
TEMP_DIR="./data/tmp"
```
Where to store temporary files. Defaults to `./data/tmp`. These files are generally short-lived and are cleaned up automatically, but if you're running out of space on `./data/tmp` you can set this to a different location.