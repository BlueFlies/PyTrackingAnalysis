import logging
import numpy as np
import pandas as pd
from . import Tracker
from . import TwoChoiceTracker
from . import Parameters
import glob
from natsort import natsorted
from . import Arena
import yaml
import os

logger = logging.getLogger(__name__)


def alias_to_group_map(counting_regions):
    """Invert a ``{group: [alias, ...]}`` design into ``{alias: group}``.

    Raw ``CountingRegion`` cells hold the *aliases* a rig writes ("L", "LL"),
    never the group key the config declares them under. Anything comparing raw
    cells against group names must map through this first.
    """
    if not counting_regions:
        return {}
    return {str(alias): group
            for group, aliases in counting_regions.items()
            for alias in aliases}


class ExperimentalDesign:
    def __init__(self, exp_name, parameters, config_path=None):
        self.experiment_name = exp_name
        self.parameters = parameters
        if config_path is not None:
            self.tracking_config_file = config_path
        else:
            data_dir = os.path.dirname(exp_name)
            if not data_dir:
                data_dir = '.'
            self.tracking_config_file = os.path.join(data_dir, 'tracking_config.yaml')
        self.tracking_regions = None
        # Counting regions is a dictionary with keys as the treatments and values as all the
        # different region aliases in the datafile that correspond to each characteristic.
        self.counting_regions = None
        try:
            self.read_yaml_config(self.tracking_config_file)
            self.experimental_design = True
        except FileNotFoundError:
            logger.warning(f"tracking_config.yaml not found: {self.tracking_config_file}")
            self.experimental_design = False
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse tracking config '{self.tracking_config_file}': {e}")
            self.experimental_design = False
        except Exception as e:
            logger.warning(f"Unexpected error reading tracking config '{self.tracking_config_file}': {e}")
            self.experimental_design = False
        self.verify_experimental_design()


    def read_yaml_config(self, file_name):
        tracking_regions = []
        counting_regions = {}
        with open(file_name, 'r') as file:
            config = yaml.safe_load(file)

        if 'tracking_regions' in config:
            for region_name, region_data in config['tracking_regions'].items():
                treatment = region_data.get('experimental_factors', '')
                x_mult = int(region_data.get('x_location_multiplier', 1))
                y_mult = int(region_data.get('y_location_multiplier', 1))
                if x_mult not in (-1, 1):
                    x_mult = 1
                if y_mult not in (-1, 1):
                    y_mult = 1
                tracking_regions.append([region_name, treatment, x_mult, y_mult])

        if 'counting_regions' in config:
            for key, value in config['counting_regions'].items():
                if 'alias' not in value:
                    raise KeyError(f"counting_regions.{key} is missing the 'alias' key")
                aliases = [x.strip() for x in value['alias'].split(',')]
                counting_regions[key] = aliases

        self.tracking_regions = pd.DataFrame(
            tracking_regions,
            columns=['RegionName', 'Treatment', 'XLocationMultiplier', 'YLocationMultiplier'],
        )
        self.counting_regions = counting_regions

    def get_tracking_region(self, region_name):
        if self.tracking_regions is None:
            return None
        return self.tracking_regions[self.tracking_regions['RegionName'] == region_name]

    def get_counting_characteristic(self, region_name):
        if self.counting_regions is None:
            return None
        for key, value in self.counting_regions.items():
            if region_name in value:
                return key
        return None

    def verify_experimental_design(self):
        if self.experimental_design == False:
            raise ValueError("An experimental design file is required for all experiments.")
        elif self.parameters.get_tracking_type() == Parameters.TrackingType.TWOCHOICETRACKER:
            if len(self.counting_regions.keys()) != 2:
                raise ValueError(
                    "Invalid design file for TwoChoiceTracker. "
                    "Must have exactly two unique counting region characteristics."
                )
        elif self.parameters.get_tracking_type() == Parameters.TrackingType.TWOCHOICECOUNTER:
            if len(self.counting_regions.keys()) != 2:
                raise ValueError(
                    "Invalid design file for TwoChoiceCounter. "
                    "Must have exactly two unique counting region characteristics."
                )

    def __str__(self):
        return (
            f"Experimental Design for {self.experiment_name}:\n"
            f"Tracking Regions:\n{self.tracking_regions}\n"
            f"Counting Regions:\n{self.counting_regions}"
        )


if __name__ == "__main__":
    p = Parameters.Parameters()
    ed = ExperimentalDesign("./Data/MaxIRSetup", p)
    print(ed.tracking_regions)
