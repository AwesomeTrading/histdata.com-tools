from histdatacom.records import Records
from multiprocessing import Queue

args = None

available_remote_data = dict()
repo_data_file_exists = False

current_queue = None
next_queue = None
csv_chunks_queue = None

batch_size = 5_000
