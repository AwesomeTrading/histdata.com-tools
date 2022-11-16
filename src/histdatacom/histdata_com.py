import sys
from pyarrow import Table
from datatable import Frame
from pandas import DataFrame
from histdatacom.cli import ArgParser
from histdatacom.options import Options
from histdatacom.utils import set_working_data_dir
from histdatacom.utils import load_influx_yaml
from histdatacom.urls import _URLs
from histdatacom.api import _API
from histdatacom.csvs import _CSVs
from histdatacom.influx import _Influx
from histdatacom.concurrency import QueueManager
from histdatacom import config


class _HistDataCom:
    """A module to pull market data from histdata.com and import it into influxDB"""

    def __init__(self,
                 records_current,
                 records_next,
                 csv_chunks_queue,
                 options):

        """ Initialization for _HistDataCom Class"""
        # Set User () or Default Arguments respectively utilizing the self.ArgParser
        # and self.Options classes.
        #   - ArgParser()():
        #       - ()(): use an IIFE to allow argparse to get garbage collected
        #       - ()(): ArgParser.__call__ returns updated Options object
        #       - vars(...): get the __dict__ representation of the object
        #       - ArgParser._arg_list_to_set(...)
        #           - Normalize iterable user arguments whose values are lists and
        #             make them sets instead
        #       - .copy(): decouple for GC using a hard copy of user args
        config.args = ArgParser._arg_list_to_set(vars(ArgParser(options)())).copy()
        config.args['default_download_dir'] = set_working_data_dir(config.args['data_directory'])
        config.args['queue_filename'] = ".queue"

        if config.args["import_to_influxdb"] == 1:
            influx_yaml = load_influx_yaml()
            config.args['INFLUX_ORG'] = influx_yaml['influxdb']['org']
            config.args['INFLUX_BUCKET'] = influx_yaml['influxdb']['bucket']
            config.args['INFLUX_URL'] = influx_yaml['influxdb']['url']
            config.args['INFLUX_TOKEN'] = influx_yaml['influxdb']['token']

        self.records_current = records_current
        self.records_next = records_next

        self.urls = _URLs(self.records_current, self.records_next)
        self.csvs = _CSVs(self.records_current, self.records_next)
        self.api = _API(self.records_current, self.records_next)

        if config.args["import_to_influxdb"] == 1:
            self.csv_chunks_queue = csv_chunks_queue
            self.influx = _Influx(self.records_current,
                                  self.records_next,
                                  self.csv_chunks_queue)

    def run(self):
        self.urls.populate_initial_queue(self.records_current, self.records_next)

        if config.args["validate_urls"]:
            self.urls.validate_urls(self.records_current, self.records_next)

        if config.args["download_data_archives"]:
            self.urls.download_zips(self.records_current, self.records_next)
            if config.args["from_api"]:
                self.api.validate_jays(self.records_current, self.records_next)
                return self.api.merge_jays(self.records_current)

        if config.args["extract_csvs"]:
            self.csvs.extract_csvs(self.records_current, self.records_next)

        if config.args["import_to_influxdb"]:
            self.influx.import_data(self.records_current,
                                    self.records_next,
                                    self.csv_chunks_queue)


def main(options: Options | None=None) -> list | Frame | DataFrame | Table:
    if not options:
        options = Options()
        QueueManager(options)(_HistDataCom)
    else:
        options.from_api = True
        return QueueManager(options)(_HistDataCom)


if __name__ == '__main__':
    sys.exit(main())
