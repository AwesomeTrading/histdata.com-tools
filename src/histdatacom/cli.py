import argparse, sys, re
from histdatacom.fx_enums import Pairs, Platform, Timeframe
from histdatacom.utils import get_current_datemonth_gmt_plus5, get_month_from_datemonth, get_year_from_datemonth

class ArgsNamespace:
    """ An intra-class DTO for Default Arguments for _HistDataCom class. """
    # argparse uses a thin class to create a namespace for cli/shell arguments to live in
    # normally argparse.ArgumentParser.parse_args(namespace=...) creates this namespace and 
    # writes user's cli args to it.  Preemptively creating here to hold default args; if the 
    # user enters args in the shell, these values will be respectively overwritten
    def __init__(self):
        self.validate_urls = True
        self.download_data_archives = False
        self.extract_csvs = False
        self.clean_data = False
        self.import_to_influxdb = False
        self.pairs = Pairs.list_keys()
        self.platforms = Platform.list_values()
        self.timeframes = Timeframe.list_keys()
        self.start_yearmonth = ""
        self.end_yearmonth = ""
        self.data_directory = "data"

class ArgParser(argparse.ArgumentParser):
    """ Encapsulation class for argparse related operations """
    
    def __init__(self, **kwargs):
        """ set up argparse, bring in defaults DTO, setup cli params, receive 
            and overwrite defaults with user cli args."""

        # init _HistDataCom.ArgParser to extend argparse.ArgumentParser
        argparse.ArgumentParser.__init__(self)

        # bring in the defaults arg DTO from outer class, use the
        # __dict__ representation of it to set argparse argument defaults.
        self.arg_namespace = ArgsNamespace()
        self._default_args = self.arg_namespace.__dict__
        self.set_defaults(**self._default_args)

        # Nothing special here, adding cli params
        # metavar="..." is used to limit the display of choices="large iterables".
        self.add_argument(
                "-V","--validate_urls",
                action='store_true',
                help='Check generated list of URLs as valid download locations')
        self.add_argument(
                "-D","--download_data_archives", 
                action='store_true',
                help='download specified pairs/platforms/timeframe and create data files')
        self.add_argument(
                "-X","--extract_csvs", 
                action='store_true',
                help='histdata.com delivers zip files.  use the -X flag to extract them to .csv.')
        self.add_argument(
                "-C","--clean_data", 
                action='store_true',
                help='{add data} headers to CSVs and convert EST(noDST) to UTC timestamp')
        self.add_argument(
                "-I","--import_to_influxdb", 
                action='store_true',
                help='import csv data to influxdb instance. Use influxdb.yaml to configure. Implies -C --clean_data')
        self.add_argument(
                '-p','--pairs',
                nargs='+',
                type=str,
                choices=Pairs.list_keys(), 
                help='space separated currency pairs. e.g. -p eurusd usdjpy ...',
                metavar='PAIR')
        self.add_argument(
                '-P','--platforms',
                nargs='+',
                type=str,
                choices=Platform.list_values(), 
                help='space separated Platforms. e.g. -P metatrader ascii ninjatrader metastock',
                metavar='PLATFORM')
        self.add_argument(
                '-t','--timeframes',
                nargs='+',
                type=(lambda v : Timeframe(v).name), # convert long Timeframe .value to short .key
                choices=Timeframe.list_keys(), 
                help='space separated Timeframes. e.g. -t tick-data-quotes 1-minute-bar-quotes ...',
                metavar='TIMEFRAME')
        self.add_argument(
                "-s","--start_yearmonth", 
                type=(lambda v : self.validate_yearmonth_format(v)),
                help='set a start year and month for data. e.g. -s 2000-04 or -s 2015-00')
        self.add_argument(
                "-e","--end_yearmonth", 
                type=(lambda v : self.validate_yearmonth_format(v)),
                help='set a start year and month for data. e.g. -s 2020-00 or -s 2022-04')
        self.add_argument(
                '-d','--data-directory',
                type=str,
                help='Not an Executable Search Path! This directory is used to perform work. default is "data" in the current directory')

        # prevent running from cli with no arguments
        if len(sys.argv)==1:
            self.print_help(sys.stderr)
            sys.exit(1)

        # Get the args from sys.argv
        self.parse_args(namespace=self.arg_namespace)

        self.check_datetime_input(self.arg_namespace)


    def __call__(self):
        """ simply return the completed args object """
        return self.arg_namespace

    @classmethod
    def _arg_list_to_set(cls, args):
        """ Utility Method to search for list objects contained in args DTO and cast them as sets """
        # This is to standardize data types. If the user specifies a parameter,
        # argparse returns a list, our defaults are sets, so . 
        for arg in args:
            if isinstance(args[arg], list): args[arg] = set(args[arg])
        return args

    @classmethod
    def check_datetime_input(cls, args_namespace):        
        if args_namespace.start_yearmonth \
          or args_namespace.end_yearmonth:
            args_namespace.start_yearmonth, args_namespace.end_yearmonth = \
                cls.check_for_start_in_yearmonth(args_namespace)

            args_namespace.start_yearmonth, args_namespace.end_yearmonth = \
                cls.check_for_now_in_yearmonth(args_namespace)

            args_namespace.start_yearmonth, args_namespace.end_yearmonth = \
                cls.check_cli_start_yearmonth(args_namespace)

            cls.check_cli_end_yearmonth(args_namespace)

            cls.check_for_same_start_yearmonth(args_namespace)

        args_namespace.start_yearmonth, args_namespace.end_yearmonth = \
            cls.replace_falsey_yearmonth_with_none(args_namespace)
        
        cls.check_start_yearmonth_in_range(args_namespace)
        cls.check_end_yearmonth_in_range(args_namespace)
        cls.check_start_lessthan_end(args_namespace)

    @classmethod
    def check_for_now_in_yearmonth(cls, args_namespace):
        if (start_yearmonth := args_namespace.start_yearmonth):
            if start_yearmonth == "now":
                return get_current_datemonth_gmt_plus5(), None
            elif end_yearmonth := args_namespace.end_yearmonth:
                if end_yearmonth == "now":
                    return start_yearmonth, get_current_datemonth_gmt_plus5()
    
        return start_yearmonth, end_yearmonth

    @classmethod
    def check_for_start_in_yearmonth(cls, args_namespace):
        try:
            if (start_yearmonth := args_namespace.start_yearmonth):
                if start_yearmonth == "start":
                    if (end_yearmonth := args_namespace.end_yearmonth):
                        if end_yearmonth == "start":
                            err_text_end_yearmonth_cannot_be_start = \
                            """
                                ERROR on -e start           ERROR
                                    * keyword 'start' cannot be used as -e start
                            """
                            raise ValueError(err_text_end_yearmonth_cannot_be_start)
                        return "200001", end_yearmonth
                    else:
                        err_text_start_must_have_end = \
                        """
                                ERROR on -s start           ERROR
                                    * keyword 'start' must also specify
                                      an end year-month
                        """ 
                        raise ValueError(err_text_start_must_have_end)
            return args_namespace.start_yearmonth, args_namespace.end_yearmonth
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def check_cli_start_yearmonth(cls, args_namespace):

        start_yearmonth = args_namespace.start_yearmonth
        start_year = get_year_from_datemonth(start_yearmonth)
        start_month = get_month_from_datemonth(start_yearmonth)

        err_text_start_month = \
        f"""
                ERROR on -e {start_yearmonth}   ERROR
                    start month cannot be zero.
                        * valid inputs:
                            a) just the year
                                eg. -s 2022
                            b) months 1-12:
                                eg. -s 2022-04
        """

        end_yearmonth = args_namespace.end_yearmonth

        err_text_no_end_yearmonth = \
        f"""
                ERROR on -e {get_year_from_datemonth(start_yearmonth)}  {end_yearmonth}  ERROR
                    * Malformed command:
                        - cannot include `-e end_year-month` when
                          specifying a single year with -s {get_year_from_datemonth(start_yearmonth)}
        """

        err_text_no_start_yearmonth = \
        f"""
                ERROR on -e {end_yearmonth}  ERROR
                    * Malformed command:
                        - cannot include `-e end_year-month` without
                          specifying a start year-month. 
                            eg. -s year-month -e year-month
        """
        err_text_start_month_greater_than_12 = \
        f"""
                ERROR on -s {start_yearmonth}  ERROR
                    * Malformed command:
                        - start month is greater than 12.
                          valid input is 01-12.
        """

        try:
            if not start_month:
                if end_yearmonth:
                    if not start_year:
                        raise ValueError(err_text_no_start_yearmonth)
                    raise ValueError(err_text_no_end_yearmonth)
                return f"{start_year}00", None
            elif start_month == "00":
                raise ValueError(err_text_start_month)
            elif int(start_month) > 12:
                raise ValueError(err_text_start_month_greater_than_12)
            else:
                return start_yearmonth, end_yearmonth
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def check_cli_end_yearmonth(cls, args_namespace):
        try:
            if end_yearmonth := args_namespace.end_yearmonth:
                end_year = get_year_from_datemonth(end_yearmonth)
                end_month = get_month_from_datemonth(end_yearmonth)

                err_text_no_endmonth = \
                f"""
                        ERROR on -e {end_yearmonth}           ERROR
                            * You left out the end month.
                                - valid input is -e year-month(1-12)
                                    eg. -e 2022-03

                """

                err_text_endmonth_cannot_be_zero = \
                f"""
                        ERROR on -e {end_yearmonth}           ERROR
                            * End month cannot be zero.
                                - valid input is -e year-month(1-12)
                                    eg. -e 2022-03

                """
                err_text_end_month_greater_than_12 = \
                f"""
                        ERROR on -e {end_yearmonth}  ERROR
                            * Malformed command:
                                - end month is greater than 12.
                                valid input is 01-12.
                """
                if end_year and not end_month:
                    raise ValueError(err_text_no_endmonth)
                elif end_month == "00":
                    raise ValueError(err_text_endmonth_cannot_be_zero)
                elif int(end_month) > 12:
                    raise ValueError(err_text_end_month_greater_than_12)
        except ValueError as err:
                cls.exit_on_datetime_error(err)

    @classmethod
    def check_for_same_start_yearmonth(cls, args_namespace):
        try:
            start_yearmonth = args_namespace.start_yearmonth
            start_year = get_year_from_datemonth(start_yearmonth)
            start_month = get_month_from_datemonth(start_yearmonth)

            end_yearmonth = args_namespace.end_yearmonth
            end_year = get_year_from_datemonth(end_yearmonth)
            end_month = get_month_from_datemonth(end_yearmonth)

            err_text_start_and_end_cannot_be_the_same = \
            f"""
                ERROR on -s {start_yearmonth} -e {end_yearmonth}  ERROR
                    * start year-month and end year-month cannot be the same.
            """

            if f"{start_year}_{start_month}" == f"{end_year}_{end_month}":
                raise ValueError(err_text_start_and_end_cannot_be_the_same)
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def replace_falsey_yearmonth_with_none(cls, args_namespace):
        start_yearmonth = args_namespace.start_yearmonth
        end_yearmonth = args_namespace.end_yearmonth

        if not start_yearmonth or start_yearmonth == "":
            start_yearmonth = None
        if not end_yearmonth or end_yearmonth == "":
            end_yearmonth = None

        return start_yearmonth, end_yearmonth

    @classmethod
    def check_start_yearmonth_in_range(cls, args_namespace):
        try:
            if start_yearmonth := args_namespace.start_yearmonth:
                err_text_date_prior_to_dataset = \
                f"""
                        ERROR on -s {start_yearmonth}      ERROR
                            * bad year-month 
                                - no data available for dates
                                prior to 2000y
                """
                err_text_date_is_in_future = \
                f"""
                        ERROR on -s {start_yearmonth}      ERROR
                            * year-month cannot be in the future.
                """
                if int(start_yearmonth) < 200000:
                    raise ValueError(err_text_date_prior_to_dataset)
                if int(start_yearmonth) > int(get_current_datemonth_gmt_plus5()):
                    raise ValueError(err_text_date_is_in_future)
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def check_end_yearmonth_in_range(cls, args_namespace):
        try:
            if end_yearmonth := args_namespace.end_yearmonth:
                err_text_date_prior_to_dataset = \
                f"""
                        ERROR on -e {end_yearmonth}     ERROR
                            * bad year-month 
                                - no data available for dates
                                prior to 2000y
                """
                err_text_date_is_in_future = \
                f"""
                        ERROR on -e {end_yearmonth}     ERROR
                            * year-month cannot be in the future.
                """
                if int(end_yearmonth) < 200000:
                    raise ValueError(err_text_date_prior_to_dataset)
                if int(end_yearmonth) > int(get_current_datemonth_gmt_plus5()):
                    raise ValueError(err_text_date_is_in_future)
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def check_start_lessthan_end(cls, args_namespace):
        try:
            if (start_yearmonth := args_namespace.start_yearmonth) \
              and (end_yearmonth := args_namespace.end_yearmonth):

                err_text_start_date_after_end_date = \
                f"""
                        ERROR on -s {start_yearmonth} -e {end_yearmonth}    ERROR
                            * logic error: end year-month is before start year-month.
                """
                if int(start_yearmonth) > int(end_yearmonth):
                    raise ValueError(err_text_start_date_after_end_date)
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def validate_yearmonth_format(cls, yearmonth):
        try:
            err_text_bad_yearmonth_format = \
            f"""
                        ERROR on {yearmonth}    ERROR
                            * invalid yearmonth format
            """

            if re.match("^\d{4}[-_.: ]\d{2}$", yearmonth) \
            or re.match("^\d{6}$", yearmonth) \
            or re.match("^\d{4}$", yearmonth) \
            or str.lower(yearmonth) == "now" \
            or str.lower(yearmonth) == "start" \
            or yearmonth == "":
                return cls.replace_date_punct(yearmonth)
            else:
                raise ValueError(err_text_bad_yearmonth_format)
        except ValueError as err:
            cls.exit_on_datetime_error(err)

    @classmethod
    def replace_date_punct(cls, datemonth_str):
        return re.sub("[-_.: ]", "", datemonth_str) if datemonth_str is not None else ""

    @classmethod
    def exit_on_datetime_error(cls, err):
        print(err)
        sys.exit(err)