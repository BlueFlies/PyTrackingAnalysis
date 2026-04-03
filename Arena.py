import logging
import numpy as np
import pandas as pd
import Tracker
import Counter
import TwoChoiceTracker
import XChoiceTracker
import TwoChoiceCounter
import PairwiseInteractionTracker
import PairwiseInteractionCounter
import Parameters
import ExperimentalDesign
import glob
from natsort import natsorted
import seaborn as sns
import matplotlib.pyplot as plt
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from collections import OrderedDict
from scipy.stats import ttest_ind
import time
import os
import random
import yaml

logger = logging.getLogger(__name__)

_RIG_MAP = {
    'small_arena':  'small_arena',
    'smallarena':   'small_arena',
    'arena_max':    'arena_max',
    'arenamax':     'arena_max',
    'colosseum':    'colosseum',
    'colloseum':    'colosseum',
    'obscura':      'obscura',
    'movie':        'movie',
}

_PARAMETER_KEYS = {
    'fps', 'mm_per_pixel', 'speed_window_seconds',
    'micromove_speed_mm_sec', 'walking_speed_mm_sec',
    'sleep_threshold_min', 'interaction_distances',
}

class Arena:
    """
    Class representing an experimental arena for tracking and analyzing data.
    """

#region ########### Initialization Functions ############
    def __init__(self, force_preprocessing=False):
        """
        Initialize the Arena object.

        Parameters:
        force_preprocessing (bool): Flag to force preprocessing of data. Currently used to override existing nearest neighbor calculations.
        """
        self.data_path = './data/'
        self.config_path = './tracking_config.yaml'

        xlsx_files = glob.glob(os.path.join(self.data_path, '*.xlsx'))
        if not xlsx_files:
            raise FileNotFoundError(f"No .xlsx file found in {self.data_path}")
        self.experiment_name = os.path.splitext(os.path.basename(xlsx_files[0]))[0]

        self.config = self._load_config()
        self.parameters = self._build_parameters()
        self.get_experiment_file_info()
        self.get_experimental_design()
        self.create_trackers(force_preprocessing)
        self.computed_summaries={}

    def _load_config(self):
        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(f"tracking_config.yaml not found at {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _build_parameters(self):
        global_cfg = self.config.get('global', {})
        tracking_type_str = global_cfg.get('tracking_type', 'TRACKER').upper()
        try:
            tracking_type = Parameters.TrackingType[tracking_type_str]
        except KeyError:
            raise ValueError(
                f"Unknown tracking_type '{tracking_type_str}' in tracking_config.yaml. "
                f"Valid values: {[t.name for t in Parameters.TrackingType]}"
            )
        rig_raw = global_cfg.get('tracking_rig', '').lower().replace(' ', '_').replace('-', '_')
        rig = _RIG_MAP.get(rig_raw, rig_raw)
        p = Parameters.Parameters()
        if rig == 'small_arena':
            p.set_small_arena_values(tracking_type)
        elif rig == 'arena_max':
            p.set_arena_max_values(tracking_type)
        elif rig in ('colosseum', 'colloseum'):
            p.set_colloseum_values(tracking_type)
        elif rig == 'obscura':
            p.set_obscura_values(tracking_type)
        elif rig == 'movie':
            fps = global_cfg.get('fps', 30)
            mm_per_pixel = global_cfg.get('mm_per_pixel', 0.1)
            p.set_movie_values(tracking_type, fps, mm_per_pixel)
        else:
            p.set_tracking_type(tracking_type)
        overrides = {k: v for k, v in global_cfg.items() if k in _PARAMETER_KEYS}
        if overrides:
            p.set(**overrides)
        return p

    def get_experiment_file_info(self):
        """
        Retrieve experiment file information from an Excel file.

        Generally not called by the user.

        :meta private:
        """
        file_name = self.data_path + self.experiment_name + '.xlsx'
        sheet_name = "ROI"
        
        roi = pd.read_excel(file_name, sheet_name=sheet_name)
        self.tracking_regions =  roi[(roi['Type']=='Tracking')].reset_index(drop=True)
        self.counting_regions =  roi[(roi['Type']=='Counting')].reset_index(drop=True)
     
    def get_experimental_design(self):        
        """
        Retrieve the experimental design.
        Generally not called by the user.
        
        :meta private:
        """
        self.experimental_design = ExperimentalDesign.ExperimentalDesign(
            self.data_path + self.experiment_name, self.parameters,
            config_path=self.config_path
        )

    def read_all_data(self):
        """
        Read all data from CSV files.
        Generally not called by the user.
        
        Returns:
        DataFrame: Concatenated DataFrame containing all data.

        :meta private:
        """
        csv_files = natsorted(glob.glob(self.data_path+self.experiment_name + "_Data_*.csv"))
        #Read each CSV file into a DataFrame and store them in a list
        dataframes = [pd.read_csv(file,keep_default_na=False,na_values=['NaN']) for file in csv_files]

        # Concatenate all DataFrames into a single DataFrame
        rd = pd.concat(dataframes, ignore_index=True)
        return rd
    
    def delete_tracker(self,region, object_id):
        """
        Delete a tracker.

        Parameters:
        tracker_id (str): ID of the tracker to delete.

        :meta private:
        """
        self.trackers.pop(f'{region}_{object_id}')
        
    
    def create_trackers(self, force_preprocessing):
        """
        Create trackers based on the experimental parameters.

        Parameters:
        force_preprocessing (bool): Flag to force preprocessing of data.

        :meta private:
        """
        rawdata = self.check_for_preprocessing(self.read_all_data(),force_preprocessing)
        tmp_trackers = {}
        if(self.parameters.get_tracking_class() == Parameters.TrackingClass.TRACKING):
            grouped_data = rawdata.groupby(['TrackingRegion','ObjectID'] )
            for (region,object_id), group in grouped_data:
                if(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
                    tracker = Tracker.Tracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
                    tracker = TwoChoiceTracker.TwoChoiceTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):                    
                    tracker = PairwiseInteractionTracker.PairwiseInteractionTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                elif(self.parameters.get_tracking_type()==Parameters.TrackingType.XCHOICETRACKER):
                    tracker = XChoiceTracker.XChoiceTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                else:
                    raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be an instance of TrackingType enum.")
                tmp_trackers[f'{region}_{object_id}'] = tracker 
            self.trackers = OrderedDict((key, tmp_trackers[key]) for key in natsorted(tmp_trackers))
        elif(self.parameters.get_tracking_class() == Parameters.TrackingClass.COUNTING):
            grouped_data = rawdata.groupby('TrackingRegion')
            for region, group in grouped_data:
                if(self.parameters.get_tracking_type()==Parameters.TrackingType.COUNTER):
                    counter = Counter.Counter(region,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICECOUNTER):
                    counter = TwoChoiceCounter.TwoChoiceCounter(region,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER):
                    counter = PairwiseInteractionCounter.PairwiseInteractionCounter(region,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
                else:
                    raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be an instance of TrackingType enum.")
                tmp_trackers[f'{region}'] = counter 
            self.trackers = OrderedDict((key, tmp_trackers[key]) for key in natsorted(tmp_trackers))
        else:
            raise ValueError(f"Invalid tracking class: {self.parameters.get_tracking_class()}. Must be an instance of TrackingClass enum.")
        self.check_for_postprocessing(rawdata) 

    def check_for_postprocessing(self,rawdata):
        """
        Check for postprocessing requirements.

        Parameters:
        rawdata (DataFrame): Raw data to be processed.

        :meta private:
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):             
            for key, tracker in self.trackers.items():
                for key2, tracker2 in self.trackers.items():
                    if(key!=key2 and tracker.get_tracking_region_id()==tracker2.get_tracking_region_id()):
                        tracker.set_neighbor(tracker2)
        
    def check_for_preprocessing(self,rawdata, force_preprocessing=False):
        """
        Check for preprocessing requirements.

        Parameters:
        rawdata (DataFrame): Raw data to be processed.
        force_preprocessing (bool): Flag to force preprocessing of data.

        Returns:
        DataFrame: Processed raw data.

        :meta private: 
        """
        ## For now we will disable this.  It should be only used if the post-processing fails
        ## because the data for partner trackers does not line up.
        if ((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) and force_preprocessing):             
            if 'ClosestNeighbor' not in rawdata.columns:
                rawdata=self.calculate_distances_for_pairwise_tracker(rawdata)
        if ((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER)):             
            #rawdata=self.calculate_distances_for_pairwise_tracker(rawdata)
            pass
        return rawdata
    
    def calculate_distances_for_pairwise_tracker(self,rawdata):
        """
        Calculate distances for pairwise interaction tracker.
        This is a somewhat slow function that churns through de novo calculates of neighbor distances.
        It can be forced by force_preprocessing=True in the constructor.
        Generally not called by the user.
        Parameters:
        rawdata (DataFrame): Raw data to be processed.

        Returns:
        DataFrame: Processed raw data with distances.

        :meta private: 
        """
        ## This works but it's pretty slow.
        # Group the data by 'TrackingRegion', 'ObjectID', and 'Frame'
        print("Calculating pairwise distances will take awhile...")
        grouped_data = rawdata.groupby(['Frame', 'TrackingRegion'])
        
        distances = []
        
        counter = 1
        print(f'Analyzing group {counter} of {len(grouped_data)}')
        for (frame, region), group in grouped_data:
            if(counter % 1000 == 0):
                print(f'Analyzing group {counter} of {len(grouped_data)}')
            counter += 1
            if len(group) == 2:
                if((group.iloc[0]['DataQuality']=="High") and (group.iloc[1]['DataQuality']=="High")):
                    x1, y1 = group.iloc[0][['X', 'Y']]
                    x2, y2 = group.iloc[1][['X', 'Y']]
                    distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    distances.extend([distance, distance])
                else:
                    distances.extend([np.nan] * len(group))
            elif group['NObjhects'].sum() == 2:
                distance = 0
                distances.extend([distance, distance])  # Add the distance for both observations
            else:
                distances.extend([np.nan] * len(group))  # Add NaN for groups that don't have exactly 2 observations

        rawdata['ClosestNeighbor'] = distances
        return rawdata
        
#endregion ########### Initialization Functions ############
    
    
#region ########### Access Functions ############
    
    def first_tracker(self):
        """
        Get the first tracker in the list in the arena.

        Returns:
        Tracker: The first tracker object.
        """
        tmp = list(self.trackers.keys())
        return self.trackers[tmp[0]]

    def get_tracker(self, key):
        """
        Get a tracker by key.

        Parameters:
        key (str): Key of the tracker.

        Returns:
        Tracker: The tracker object.
        """
        return self.trackers.get(key,None)

    def get_random_tracker(arena):
        """
        Returns a random tracker from the arena's trackers.
        Assumes arena.trackers is a dict or list of tracker objects.
        """
        # If trackers is a dict, get the values as a list
        if isinstance(arena.trackers, dict):
            trackers = list(arena.trackers.values())
        else:
            trackers = list(arena.trackers)
        if not trackers:
            return None  # or raise an Exception if preferred
        return random.choice(trackers)
#endregion ########### Access Functions ############

#region ########### Basic Computation Functions ############
    def summarize_facet(self,cutoffs=(10,70),copy_to_clipboard=False, write_to_csvfile=False, remove_partners=False):
        """
        Summarize data in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        copy_to_clipboard (bool): Flag to copy results to clipboard.
        write_to_csvfile (bool): Flag to write results to CSV file.
        remove_partners (bool): Flag to remove partners from the summary. This is relevant for pairwise data where pairs may have identical values (e.g., interaction percentage).

        Returns:
        DataFrame: Summarized data.
        """
        if(isinstance(cutoffs, tuple)):
            cutoffs = list(cutoffs)
        elif(isinstance(cutoffs, int)):
            cutoffs = [cutoffs]
        else:
            raise ValueError("Invalid cutoffs. Must be a tuple or asingle integer")
        cutoffs.insert(0,0)
        cutoffs.append(float('inf'))
        results = []
        for i in range(len(cutoffs)-1):
            tmp = self.summarize(range_minutes=tuple([cutoffs[i],cutoffs[i+1]]),remove_partners=remove_partners)
            tmp['FacetRange']=[tuple([cutoffs[i],cutoffs[i+1]])]*len(tmp)
            results.append(tmp)
        all_summaries = pd.concat(results, ignore_index=True)        
        if(copy_to_clipboard):            
            all_summaries.to_clipboard(index=False, na_rep='NA')
        if(write_to_csvfile==True):                        
            all_summaries.to_csv(f"{self.data_path+self.experiment_name}_Summary_Facet_NA.csv",index=False, na_rep='NA')      
        return all_summaries
    
    
    def print_short_data_quality_report(self,cutoff=0.9,range_minutes=(0,0)):
        """
        Print a short data quality report.

        Parameters:
        range_minutes (tuple): Range of minutes to summarize.

        Returns:
        DataFrame: Short data quality report.
        """
        data_quality = self.get_data_quality(range_minutes)                
        print(data_quality)
        
        warning_data=data_quality[(data_quality['HighQuality']<cutoff)]
        if(len(warning_data)>0):
            print("****************************************************")
            print(f"Warning: Some data quality falls below {cutoff}!")
            print(warning_data)
            print("****************************************************")            
        else:
            print("****************************************************")
            print(f"All data quality is above {cutoff}.")            
            print("****************************************************")            
            
    
    def get_data_quality(self,range_minutes=(0,0)):
        """
        Print data quality.

        Generally not called by the user.
        
        :meta private:
        """
        
        combined_results = []

        for key, tracker in self.trackers.items():
            data_quality = tracker.get_data_quality(range_minutes)
            data_quality['Tracker'] = key  # Add a column to identify the tracker
            combined_results.append(data_quality)

        # Concatenate all results into a single DataFrame
        combined_df = pd.concat(combined_results, ignore_index=True)

        # Move the last column to the first position
        last_column = combined_df.pop(combined_df.columns[-1])
        combined_df.insert(0, last_column.name, last_column)

        return combined_df        

    def summarize(self,range_minutes=(0,0),copy_to_clipboard=False, write_to_csvfile=False, remove_partners=False):
        """
        Summarize data.

        Parameters:
        range_minutes (tuple): Range of minutes to summarize.
        copy_to_clipboard (bool): Flag to copy results to clipboard.
        write_to_csvfile (bool): Flag to write results to CSV file.
        remove_partners (bool): Flag to remove partners from the summary.This is relevant for pairwise data where pairs may have identical values (e.g., interaction percentage).

        Returns:
        DataFrame: Summarized data.
        """
        ## Remember when returning partners we don't take shortcuts to avoid confustion.
        if(remove_partners==False):
            if(range_minutes in self.computed_summaries):
                return self.computed_summaries[range_minutes]
        
        summaries = []
        for key, tracker in self.trackers.items():
            summary = tracker.summarize(range_minutes)
            summaries.append(summary)
    
        # Concatenate all summaries into a single DataFrame
        all_summaries = pd.DataFrame(summaries)
        
        if(remove_partners):
            all_summaries = all_summaries.drop_duplicates(subset="TrackingRegion",keep="first")
            all_summaries.reset_index(drop=True, inplace=True)
        else:
            ## To avoid confusion, if we remove partners, we won't save a copy to speed things up.
            self.computed_summaries[range_minutes] = all_summaries

   
        ## Note that for the this function to work in linux, you need to install xclip or xsel (verified with xclip)
        if(copy_to_clipboard):            
            all_summaries.to_clipboard(index=False, na_rep='NA')
        if(write_to_csvfile==True):            
            all_summaries.to_csv(f"{self.data_path+self.experiment_name}_Summary.csv",index=False, na_rep='NA') 
        return all_summaries
    
#endregion ########### Basic Computation Functions ############

#region ########### User Plotting Functions ############
    def plot_pi(self, range_minutes=(0,0)):      
        """
        Plot preference index (PI).

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_pi_facet(self,cutoffs=(10,70)):
        """
        Plot PI in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_facet_twochoicetracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICECOUNTER):
            self.plot_pi_facet_twochoicecounter(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_percentage(self, range_minutes=(0,0)):      
        """
        Plot choice percentage.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")  
    def plot_percentage_facet(self,cutoffs=(10,70)):
        """
        Plot choice percentage in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_facet_twochoicetracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICECOUNTER):
            self.plot_percentage_facet_twochoicecounter(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_adjusted_x_position(self,range_minutes=(0,0)):
        """
        Plot adjusted X position (adjusted for polarity as defined in the experimental design).

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.XCHOICETRACKER):
            self.plot_adj_x_pos_xchoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be an XChoiceTracker.")
    def plot_adjusted_x_position_facet(self,cutoffs=(10,70)):
        """
        Plot adjusted X position (adjusted for polarity in the experimental design file) in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.XCHOICETRACKER):
            self.plot_adj_x_pos_facet_xchoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be an XChoiceTracker.")
    def plot_totaldistance(self, range_minutes=(0,0)):      
        """
        Plot total distance moved (mm).

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        else:
            pass
    def plot_totaldistance_facet(self,cutoffs=(10,70)):
        """
        Plot total distance moved (mm) in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        else:
            pass

    def plot_trackers_percentages(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        """
        Plot cumulative and time-dependent choice percentages on the same plot and for each tracker individually.

        Parameters:
        window_size_min (int): Window size in minutes for time dependent analysis.
        step_size_min (int): Step size in minutes for time dependent analysis.
        range_minutes (tuple): Range of minutes to plot.
        show_light (bool): Flag to show light.
        """
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER) or \
            (self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICECOUNTER)):
            for key, tracker in self.trackers.items():
                tracker.plot_percentages(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    
    def plot_trackers_pis(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        """
        Plot trackers' cumulative and time-dependent preference indices (PIs) on the same plot and for each tracker individually.

        Parameters:
        window_size_min (int): Window size in minutes for time dependent analysis.
        step_size_min (int): Step size in minutes for time dependent analysis.
        range_minutes (tuple): Range of minutes to plot.
        show_light (bool): Flag to show light.
        """
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER) or \
            (self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICECOUNTER)):
            for key, tracker in self.trackers.items():
                tracker.plot_pis(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")

    def plot_trackers_x_hist(self,range_minutes=(0,0)):
        """
        Plot histogram of each tracker's X positions.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_class() == Parameters.TrackingClass.COUNTING): 
            raise ValueError(f"Invalid tracking class: {self.parameters.get_tracking_class()}. Must be a Tracker.")
        for key, tracker in self.trackers.items():
            tracker.plot_x_hist(range_minutes)            

    def plot_trackers_x(self,range_minutes=(0,0),one_plot=False):
        """
        Plot each tracker's X positions. This function automatically adjusts the X positions based on the experimental design file.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        one_plot (bool): Flag to plot all trackers in one plot.
        """
        if(self.parameters.get_tracking_class() == Parameters.TrackingClass.COUNTING): 
            raise ValueError(f"Invalid tracking class: {self.parameters.get_tracking_class()}. Must be a Tracker.")
        if(one_plot):
            for treatment in self.experimental_design.tracking_regions['Treatment'].unique():        
                fig, ax = plt.subplots(figsize=(10, 6))
            
                # Generate a colormap
                colormap = plt.cm.get_cmap('tab10', len(self.trackers))
                
                for idx, (key, tracker) in enumerate(self.trackers.items()):
                    if(tracker.get_treatment()==treatment):
                        # Assuming tracker has a method to get x-positions within the specified range
                        x_positions = tracker.get_x_positions(range_minutes)
                        minutes = tracker.get_minutes(range_minutes)
                        ax.plot(minutes,x_positions, label=key, color=colormap(idx),alpha=0.7)
                
                ax.set_xlabel('Minutes')
                ax.set_ylabel('X Position')
                title = treatment + " (Axis flips applied if specified)"
                ax.set_title(title)            
                plt.show()            
        else:                     
            for key, tracker in self.trackers.items():
                tracker.plot_x(range_minutes)            

    def plot_trackers_y(self,range_minutes=(0,0),one_plot=False):
        """
        Plot trackers' Y positions. This function automatically adjusts the Y positions based on the experimental design file.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        one_plot (bool): Flag to plot all trackers in one plot.
        """
        if(self.parameters.get_tracking_class() == Parameters.TrackingClass.COUNTING): 
            raise ValueError(f"Invalid tracking class: {self.parameters.get_tracking_class()}. Must be a Tracker.")
        
        if(one_plot):
            for treatment in self.experimental_design.tracking_regions['Treatment'].unique():        
                fig, ax = plt.subplots(figsize=(10, 6))
            
                # Generate a colormap
                colormap = plt.cm.get_cmap('tab10', len(self.trackers))
                
                for idx, (key, tracker) in enumerate(self.trackers.items()):
                    if(tracker.get_treatment()==treatment):
                        # Assuming tracker has a method to get x-positions within the specified range
                        y_positions = tracker.get_y_positions(range_minutes)
                        ax.plot(y_positions, label=key, color=colormap(idx),alpha=0.7)
                
                ax.set_xlabel('Minutes')
                ax.set_ylabel('Y Position')
                title = treatment + " (Axis flips applied if specified)"
                ax.set_title(title)            
                plt.show()            
        else:            
            for key, tracker in self.trackers.items():
                tracker.plot_y(range_minutes)
            
    def plot_trackers_xy(self,range_minutes=(0,0)):
        """
        Plot trackers' XY positions. This function automatically adjusts the X and Y positions based on the experimental design file.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
     
    def plot_trackers_x_hist(self,bins=30,range_minutes=(0,0)):
        """
        Plot histogram of trackers' X positions. This function automatically adjusts the X positions based on the experimental design file.

        Parameters:
        bins (int): Number of bins for the histogram.
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.XCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_x_hist(bins=bins,range_minutes=range_minutes)
      
    def plot_trackers_time_dependent_interactions(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        """
        Plot time-dependent interactions of trackers.

        Parameters:
        window_size_min (int): Window size in minutes.
        step_size_min (int): Step size in minutes.
        range_minutes (tuple): Range of minutes to plot.
        """
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) or (self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER)):
            last_region = None
            for key, tracker in self.trackers.items():
                if(tracker.tracking_region_id!=last_region):
                    tracker.plot_time_dependent_interactions(window_size_min,step_size_min,range_minutes)
                    last_region = tracker.tracking_region_id
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a PairwiseInteractionTracker.")
   
    def plot_transitions(self,range_minutes=(0,0)):
        """
        Plot transitions.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
  
    def plot_interactions(self,range_minutes=(0,0)):
        """
        Plot interactions.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) or (self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER)):
            self.plot_interactions_pairwiseinteractiontracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
      
    def plot_interactions_facet(self,cutoffs=(10,70)):
        """
        Plot interactions in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) or (self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER)):
            self.plot_interactions_facet_pairwiseinteractiontracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
        
    def plot_transitions_facet(self,cutoffs=(10,70)):
        """
        Plot transitions in facets.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    
#endregion ########### User Plotting Functions ############


#region ########### Backend Plotting ############
    def plot_pi_twochoicetracker(self, range_minutes=(0,0)):
        """
        Backend function to plot PI for TwoChoiceTracker.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='FinalPI', data=summary_data, jitter=True,  hue='Transitions')
        tmp = f"PI Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('PI')
        plt.ylim(-1.1,1.1)
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['FinalPI'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        
        tmp = list(self.experimental_design.counting_regions.keys())        
        ax.text(-0.4,1,tmp[0])
        ax.text(-0.4,-1,tmp[1])
        plt.show()

    def plot_pi_twochoicecounter(self, range_minutes=(0,0)):
        """
        Backend function to plot PI for TwoChoiceTracker.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='FinalPI', data=summary_data, jitter=True)
        tmp = f"PI Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('PI')
        plt.ylim(-1.1,1.1)
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['FinalPI'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        
        tmp = list(self.experimental_design.counting_regions.keys())        
        ax.text(-0.4,1,tmp[0])
        ax.text(-0.4,-1,tmp[1])
        plt.show()
    
    def plot_transitions_twochoicetracker(self, range_minutes=(0,0)):
        """
        Backend function to plot transitions for TwoChoiceTracker.
        Generally not called by the user.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='TransitionsPerMin', data=summary_data, jitter=True,  hue='FinalPI')
        tmp = f"Transitions Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('Transitions (transitions/min)')        
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['TransitionsPerMin'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
               
        plt.show()

    def plot_pi_facet_twochoicetracker(self, cutoffs=(10,70)):   
        """
        Backend function to plot PI in facets for TwoChoiceTracker.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='FinalPI', hue='Transitions', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['FinalPI'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            tmp = list(self.experimental_design.counting_regions.keys())        
            ax.text(-0.4,1,tmp[0])
            ax.text(-0.4,-1,tmp[1])
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'PI')
        g.set(ylim=(-1.1, 1.1))
        
        plt.show()

    def plot_pi_facet_twochoicecounter(self, cutoffs=(10,70)):   
        """
        Backend function to plot PI in facets for TwoChoiceCounter.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='FinalPI', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['FinalPI'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            tmp = list(self.experimental_design.counting_regions.keys())        
            ax.text(-0.4,1,tmp[0])
            ax.text(-0.4,-1,tmp[1])
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'PI')
        g.set(ylim=(-1.1, 1.1))
        
        plt.show()


    def plot_transitions_facet_twochoicetracker(self, cutoffs=(10,70)):   
        """
        Backend function to plot transitions in facets for TwoChoiceTracker.
        Generally not called by the user.   

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='TransitionsPerMin', hue='FinalPI', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['TransitionsPerMin'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            plt.xlim(-.5,ntreatments-1+0.5)
            
        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4,sharey=False)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Transitions (transitions/min)')        
        
        plt.show()

    def plot_percentage_twochoicetracker(self, range_minutes=(0,0)):
        """
        Backend function to plot percentage for TwoChoiceTracker.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='FinalPercentage', data=summary_data, jitter=True,  hue='Transitions')
        tmp = f"Percentage Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('Percentage')
        plt.ylim(-0.05,1.05)
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['FinalPercentage'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        tmp = list(self.experimental_design.counting_regions.keys())        
        ax.text(-0.4,1,tmp[0])
        ax.text(-0.4,-1,tmp[1])
        plt.show()

    def plot_percentage_twochoicecounter(self, range_minutes=(0,0)):
        """
        Backend function to plot percentage for TwoChoiceTracker.

        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='FinalPercentage', data=summary_data, jitter=True)
        tmp = f"Percentage Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('Percentage')
        plt.ylim(-0.05,1.05)
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['FinalPercentage'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        tmp = list(self.experimental_design.counting_regions.keys())        
        ax.text(-0.4,1,tmp[0])
        ax.text(-0.4,-1,tmp[1])
        plt.show()
    
    def plot_adj_x_pos_facet_xchoicetracker(self, cutoffs=(10,70)):
        """
        Backend function to plot adjusted X position in facets for XChoiceTracker.
        Generally not called by the user.

        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='AvgAdjX_mm', hue='TotalXDistance_mm', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['AvgAdjX_mm'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Avg Adjusted X Position')
        
        plt.show()
         
    def plot_adj_x_pos_xchoicetracker(self, range_minutes=(0,0)):
        """
        Backend function to plot adjusted X position for XChoiceTracker.
        Generally not called by the user.
        
        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='AvgAdjX_mm', data=summary_data, jitter=True,  hue='TotalXDistance_mm')
        tmp = f"Percentage Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('Avg Adjusted X Position')
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['AvgAdjX_mm'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        plt.show()
        
    def plot_interactions_pairwiseinteractiontracker(self, range_minutes=(0,0)):
        """
        Backend function to plot interactions for PairwiseInteractionTracker.
        Generally not called by the user.
        
        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes, remove_partners=True)
        print(summary_data )
        ## Remember we need to ensure only one of the pair is included.
        for dist_column in [f"PercentInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]:
            plt.figure(figsize=(10, 6))
            p=sns.stripplot(x='Treatment', y=dist_column, data=summary_data, jitter=True)
            tmp = f"{dist_column} Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
            plt.title(tmp)
            plt.xlabel('Treatment')
            plt.ylabel('Fraction Frames Interacting')
            plt.ylim(-0.05,1.05)
            ntreatments = summary_data['Treatment'].nunique()
            plt.xlim(-.5,ntreatments-1+0.5)

            df_mean = summary_data.groupby('Treatment', sort=False)[dist_column].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in df_mean.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            plt.show()

    def plot_interactions_facet_pairwiseinteractiontracker(self, cutoffs=(10,70)):   
        """
        Backend function to plot interactions in facets for PairwiseInteractionTracker.
        Generally not called by the user.
        
        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs,remove_partners=True)
        def custom_plot(data, colname, **kwargs):
                p=sns.stripplot(x='Treatment', y=colname, data=data, jitter=True, **kwargs)
                means = data.groupby('Treatment', sort=False)[colname].mean()
                ax = plt.gca()
                x_coords = ax.get_xticks()
                counter=0
                for i, y in means.items():
                    p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                    counter+=1
                ntreatments = data['Treatment'].nunique() 
                plt.title(colname)
                plt.xlim(-.5,ntreatments-1+0.5)
                
        for dist_column in [f"PercentInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]:
            # Create the FacetGrid
            g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
            #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
            g.map_dataframe(custom_plot,colname=dist_column)
            # Add titles and labels
            g.set_titles(col_template="Facet Range (min): {col_name}")
            g.set_axis_labels('Treatment', 'Fraction Frames Interacting')
            g.set(ylim=(-.05, 1.05))
            g.fig.suptitle(dist_column)
            plt.subplots_adjust(top=0.87)  # Adjust the top to make room for the title
            plt.show()

    def plot_percentage_facet_twochoicetracker(self, cutoffs=(10,70)):   
        """
        Backend function to plot percentage in facets for TwoChoiceTracker.
        Generally not called by the user.
        
        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='FinalPercentage', hue='Transitions', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['FinalPercentage'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            tmp = list(self.experimental_design.counting_regions.keys())        
            ax.text(-0.4,1,tmp[0])
            ax.text(-0.4,0,tmp[1])
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Percentage')
        g.set(ylim=(-.05, 1.05))
        
        plt.show()

    def plot_percentage_facet_twochoicecounter(self, cutoffs=(10,70)):   
        """
        Backend function to plot percentage in facets for TwoChoiceTracker.
        Generally not called by the user.
        
        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='FinalPercentage', data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['FinalPercentage'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            tmp = list(self.experimental_design.counting_regions.keys())        
            ax.text(-0.4,1,tmp[0])
            ax.text(-0.4,0,tmp[1])
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Percentage')
        g.set(ylim=(-.05, 1.05))
        
        plt.show()


    def plot_totaldistance_generaltracker(self, range_minutes=(0,0)):
        """
        Backend function to plot total distance for general tracker.
        Generally not called by the user.
        
        Parameters:
        range_minutes (tuple): Range of minutes to plot.
        """
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='TotalDistancePerMin', data=summary_data, jitter=True)
        tmp = f"Distance Range Minutes = [{summary_data["StartMinutes"].min():.2f} , {summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('Distance (mm/min)')
        ntreatments = summary_data['Treatment'].nunique()
        plt.xlim(-.5,ntreatments-1+0.5)

        df_mean = summary_data.groupby('Treatment', sort=False)['TotalDistancePerMin'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        tmp = list(self.experimental_design.counting_regions.keys())             
        plt.show()

    def plot_totaldistance_facet_generaltracker(self, cutoffs=(10,70)):   
        """
        Backend function to plot total distance in facets for general tracker.
        Generally not called by the user.
        
        Parameters:
        cutoffs (tuple): Cutoff values for facets.
        """
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='TotalDistancePerMin',data=data, jitter=True, **kwargs)
            means = data.groupby('Treatment', sort=False)['TotalDistancePerMin'].mean()
            ax = plt.gca()
            x_coords = ax.get_xticks()
            counter=0
            for i, y in means.items():
                p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
                counter+=1
            ntreatments = data['Treatment'].nunique()
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4, sharey=False)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Distance (mm/min)')        
        
        plt.show()

#endregion ########### Backend Plotting ############

#region ########### Special Analysis Functions ############

    def analyze_rle_data(self, change_none_to_light=True, min_duration_frames=1, range_minutes=(0, 0)):
        """
        Analyze RLE (Run Length Encoding) of choice behavior for all TwoChoiceTrackers.

        Parameters:
        change_none_to_light (bool): Replace 'None' region values with the first counting region name.
        min_duration_frames (int): Minimum run length in frames; shorter runs are removed.
        range_minutes (tuple): Time window to analyze; (0, 0) means all data.

        Returns:
        DataFrame: Per-tracker RLE statistics including mean and median run lengths per choice.
        """
        from Parameters import TrackingType
        if self.parameters.get_tracking_type() != TrackingType.TWOCHOICETRACKER:
            raise ValueError(
                f"Invalid tracking type: {self.parameters.get_tracking_type()}. "
                "analyze_rle_data requires TwoChoiceTracker."
            )

        results = []
        for key, tracker in self.trackers.items():
            rle_data = tracker.rle(range_minutes)

            if change_none_to_light:
                first_region = list(tracker.counting_regions_design.keys())[0] if tracker.counting_regions_design else "Light"
                rle_data['values'] = rle_data['values'].replace("None", first_region)
                changes = rle_data['values'].ne(rle_data['values'].shift()).cumsum()
                rle_data = rle_data.groupby(changes, as_index=False).agg({'lengths': 'sum', 'values': 'first'})

            if min_duration_frames > 1:
                rle_data = rle_data[rle_data['lengths'] >= min_duration_frames].reset_index(drop=True)
                if len(rle_data) > 0:
                    changes = rle_data['values'].ne(rle_data['values'].shift()).cumsum()
                    rle_data = rle_data.groupby(changes, as_index=False).agg({'lengths': 'sum', 'values': 'first'})

            treatment = tracker.tracking_region_design['Treatment'].iloc[0] if tracker.tracking_region_design is not None else "Unknown"
            counting_names = list(tracker.counting_regions_design.keys()) if tracker.counting_regions_design is not None else ["Treatment1", "Treatment2"]
            t1_name = counting_names[0] if len(counting_names) > 0 else "Treatment1"
            t2_name = counting_names[1] if len(counting_names) > 1 else "Treatment2"

            rle_filtered = rle_data[rle_data['values'] != "None"]
            t1_data = rle_filtered[rle_filtered['values'] == t1_name]
            t2_data = rle_filtered[rle_filtered['values'] == t2_name]

            results.append({
                'Tracker': key,
                'Treatment': treatment,
                'Treatment1_Name': t1_name,
                'Treatment2_Name': t2_name,
                'Treatment1_Rows': len(t1_data),
                'Treatment2_Rows': len(t2_data),
                'Treatment1_MeanLength': t1_data['lengths'].mean() if len(t1_data) > 0 else 0,
                'Treatment2_MeanLength': t2_data['lengths'].mean() if len(t2_data) > 0 else 0,
                'Treatment1_MedianLength': t1_data['lengths'].median() if len(t1_data) > 0 else 0,
                'Treatment2_MedianLength': t2_data['lengths'].median() if len(t2_data) > 0 else 0,
                'Treatment1_Lengths': t1_data['lengths'].tolist(),
                'Treatment2_Lengths': t2_data['lengths'].tolist(),
            })

        return pd.DataFrame(results)

    def analyze_rle_data_facet(self, cutoffs=(10, 70), change_none_to_light=True,
                               min_duration_frames=1, write_to_csvfile=False):
        """
        Faceted version of analyze_rle_data across time windows.

        Parameters:
        cutoffs (tuple|int): Facet boundary minutes.
        write_to_csvfile (bool): If True, saves results to the data directory.

        Returns:
        DataFrame: RLE statistics with a FacetRange column.
        """
        if isinstance(cutoffs, tuple):
            cutoffs = list(cutoffs)
        elif isinstance(cutoffs, int):
            cutoffs = [cutoffs]
        else:
            raise ValueError("cutoffs must be a tuple or a single integer.")
        cutoffs.insert(0, 0)
        cutoffs.append(float('inf'))

        results = []
        for i in range(len(cutoffs) - 1):
            tmp = self.analyze_rle_data(
                change_none_to_light=change_none_to_light,
                min_duration_frames=min_duration_frames,
                range_minutes=(cutoffs[i], cutoffs[i + 1]),
            )
            tmp['FacetRange'] = [tuple([cutoffs[i], cutoffs[i + 1]])] * len(tmp)
            results.append(tmp)

        all_results = pd.concat(results, ignore_index=True)
        if write_to_csvfile:
            path = f"{self.data_path}{self.experiment_name}_EventDuration_Summary_Facet.csv"
            all_results.to_csv(path, index=False)
        return all_results

    def analyze_distance_by_light(self, range_minutes=(0, 0)):
        """
        Analyze distance moved and time spent in each counting region (e.g. Light vs NoLight).

        For each tracker the function sums Dist_mm and DeltaSec within each group of counting
        regions as defined by the experimental design, then computes mm/sec speed for each group.

        Parameters:
        range_minutes (tuple): Time window; (0, 0) means all data.

        Returns:
        DataFrame: Per-tracker distance and time totals for each counting region group.
        """
        results = []
        for key, tracker in self.trackers.items():
            data_subset = tracker.get_data_subset(range_minutes)
            treatment = tracker.tracking_region_design['Treatment'].iloc[0] if tracker.tracking_region_design is not None else "Unknown"

            if tracker.counting_regions_design is None:
                continue
            if 'CountingRegion' not in data_subset.columns:
                continue

            group_names = list(tracker.counting_regions_design.keys())
            # Heuristic: first group matching "light" (and not "no") is Light; next is NoLight.
            light_group, nolight_group = None, None
            for g in group_names:
                g_lower = g.lower()
                if 'light' in g_lower and 'no' not in g_lower:
                    light_group = g
                elif 'no' in g_lower and 'light' in g_lower:
                    nolight_group = g
            if light_group is None or nolight_group is None:
                if len(group_names) >= 2:
                    light_group, nolight_group = group_names[0], group_names[1]
                else:
                    continue

            light_vals = tracker.counting_regions_design[light_group]
            nolight_vals = tracker.counting_regions_design[nolight_group]

            light_data = data_subset[data_subset['CountingRegion'].isin(light_vals)]
            nolight_data = data_subset[data_subset['CountingRegion'].isin(nolight_vals)]

            light_dist = light_data['Dist_mm'].sum() if 'Dist_mm' in light_data.columns else 0
            nolight_dist = nolight_data['Dist_mm'].sum() if 'Dist_mm' in nolight_data.columns else 0
            light_time = light_data['DeltaSec'].sum() if 'DeltaSec' in light_data.columns else 0
            nolight_time = nolight_data['DeltaSec'].sum() if 'DeltaSec' in nolight_data.columns else 0

            row = {
                'Tracker': key,
                'Treatment': treatment,
                f'{light_group}_Distance_mm': light_dist,
                f'{nolight_group}_Distance_mm': nolight_dist,
                f'{light_group}_Time_sec': light_time,
                f'{nolight_group}_Time_sec': nolight_time,
            }
            with np.errstate(divide='ignore', invalid='ignore'):
                row[f'{light_group}_Distance_mm_sec'] = np.where(light_time > 0, light_dist / light_time, np.nan)
                row[f'{nolight_group}_Distance_mm_sec'] = np.where(nolight_time > 0, nolight_dist / nolight_time, np.nan)
            results.append(row)

        return pd.DataFrame(results)

    def analyze_distance_by_light_facet(self, cutoffs=(10, 70), copy_to_clipboard=False,
                                        write_to_csvfile=False):
        """
        Faceted version of analyze_distance_by_light across time windows.

        Parameters:
        cutoffs (tuple|int): Facet boundary minutes.
        copy_to_clipboard (bool): Copy result to clipboard.
        write_to_csvfile (bool): Save result to the data directory.

        Returns:
        DataFrame: Distance/time statistics with a FacetRange column.
        """
        if isinstance(cutoffs, tuple):
            cutoffs = list(cutoffs)
        elif isinstance(cutoffs, int):
            cutoffs = [cutoffs]
        else:
            raise ValueError("cutoffs must be a tuple or a single integer.")
        cutoffs.insert(0, 0)
        cutoffs.append(float('inf'))

        results = []
        for i in range(len(cutoffs) - 1):
            tmp = self.analyze_distance_by_light(range_minutes=(cutoffs[i], cutoffs[i + 1]))
            tmp['FacetRange'] = [tuple([cutoffs[i], cutoffs[i + 1]])] * len(tmp)
            results.append(tmp)

        all_results = pd.concat(results, ignore_index=True)
        if copy_to_clipboard:
            all_results.to_clipboard(index=False)
        if write_to_csvfile:
            path = f"{self.data_path}{self.experiment_name}_DistanceByLight_Facet.csv"
            all_results.to_csv(path, index=False)
        return all_results

#endregion ########### Special Analysis Functions ############

#region ########### Statistical Functions ############
    def run_pairwise_comparisons(self, metric='FinalPI', range_minutes=(0,0)):
        """
        Run pairwise comparisons for a given metric.
        Generally not called by the user.
        
        Parameters:
        metric (str): Metric to compare.
        range_minutes (tuple): Range of minutes to compare.
        """
        remove_partners = False
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) and ("Interacting" in metric)):
            remove_partners=True
        summary = self.summarize(range_minutes, remove_partners=remove_partners)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        # Perform pairwise t-tests
        treatments = summary['Treatment'].unique()

        if(len(treatments)<2):
            print("There must be at least two treatments to compare.")
        elif(len(treatments)==2):
            group1 = pd.to_numeric(summary[summary['Treatment'] == treatments[0]][metric], errors='coerce').dropna()
            group2 = pd.to_numeric(summary[summary['Treatment'] == treatments[1]][metric], errors='coerce').dropna()
            if len(group1) == 0 or len(group2) == 0:
                print(f"Warning: Insufficient numeric data for {metric} comparison. Skipping.")
                return
            t_stat, p_value = ttest_ind(group1, group2)
            print("############# T-Test #############")
            print(f"Column = {metric}, Range Minutes = ({range_minutes[0]:.2f} , {range_minutes[1]:.2f}) ")
            print(f"{treatments[0]} vs. {treatments[1]}: T={t_stat:.2f}, p={p_value:.5f}")
        else:
            metric_numeric = pd.to_numeric(summary[metric], errors='coerce')
            valid_mask = metric_numeric.notna()
            if valid_mask.sum() == 0:
                print(f"Warning: No valid numeric data for {metric} comparison. Skipping.")
                return
            tukey = pairwise_tukeyhsd(endog=metric_numeric[valid_mask], groups=summary['Treatment'][valid_mask], alpha=0.05)            
            print(f"Column = {metric}, Range Minutes = [{range_minutes[0]:.2f} , {range_minutes[1]:.2f}] ")
            print(tukey)
    
    def run_pairwise_comparisons_facet(self, metric='FinalPI', cutoffs=(10,70), remove_partners=False):
        """
        Run pairwise comparisons in facets for a given metric.
        Generally not called by the user.
        
        Parameters:
        metric (str): Metric to compare.
        cutoffs (tuple): Cutoff values for facets.
        remove_partners (bool): Flag to remove partners from the comparison.
        """
        summary = self.summarize_facet(cutoffs, remove_partners=remove_partners)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        for frange in summary['FacetRange'].unique():
            subset = summary[summary['FacetRange'] == frange]
            treatments = subset['Treatment'].unique()
            if(len(treatments)<2):
                print("There must be at least two treatments to compare.")
            elif(len(treatments)==2):
                group1 = pd.to_numeric(subset[subset['Treatment'] == treatments[0]][metric], errors='coerce').dropna()
                group2 = pd.to_numeric(subset[subset['Treatment'] == treatments[1]][metric], errors='coerce').dropna()
                if len(group1) == 0 or len(group2) == 0:
                    print(f"Warning: Insufficient numeric data for {metric} in facet {frange}. Skipping.")
                    print("\n")
                    continue
                t_stat, p_value = ttest_ind(group1, group2)
                print("############# T-Test #############")
                print(f"Column = {metric}, Range Minutes = ({frange[0]:.2f} , {frange[1]:.2f}) ")
                print(f"{treatments[0]} vs. {treatments[1]}: T={t_stat:.2f}, p={p_value:.5f}")
                print("\n")
            else:              
                metric_numeric = pd.to_numeric(subset[metric], errors='coerce')
                valid_mask = metric_numeric.notna()
                if valid_mask.sum() == 0:
                    print(f"Warning: No valid numeric data for {metric} in facet {frange}. Skipping.")
                    print("\n")
                    continue
                tukey = pairwise_tukeyhsd(endog=metric_numeric[valid_mask], groups=subset['Treatment'][valid_mask], alpha=0.05)
                print(f"Column = {metric}, Facet Range = ({frange[0]:.2f},{frange[1]:.2f})")
                print(tukey)
                print("\n")
            
#endregion ########### Statistical Functions ############        

#region ########### QC Functions ############


#endregion ########### QC Functions ############    
if __name__ == "__main__":
    """
    Main function to test the Arena class.
    """
    p=Parameters.Parameters()
    #p.set_small_arena_values(Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER)
    #p.set_pairwise_interactioncounter_values_arena_max([2,4,8])
    #p.set_movie_values(Parameters.TrackingType.TWOCHOICETRACKER, 10, 0.056)
    p.set_colloseum_values(Parameters.TrackingType.TWOCHOICETRACKER)         
    arena = Arena(p,data_path="./Data/")
    arena.delete_tracker("T_23","0")
    arena.print_short_data_quality_report()
    #print(arena.get_data_quality())
    #print(arena.first_tracker().rawdata[['ClosestNeighbor','IsNeighborValid']].head(30))
    #arena.first_tracker().plot_cumulative_percentage(range_minutes=(0,0),show_light=True)
    #print(arena.summarize_facet(cutoffs=(10,15)))
    #arena.run_pairwise_comparisons_facet(metric="VarAdjX_mm",cutoffs=(10,15))
    #arena.plot_adjusted_x_position_facet(cutoffs=(10,15))
    #arena.plot_trackers_x()
    #arena.summarize_facet(cutoffs=(10,70),remove_partners=True)
    #arena.plot_trackers_time_dependent_interactions()
    #print(arena.first_tracker().plot_time_dependent_distances())
    #arena.run_pairwise_comparisons_facet(cutoffs=(10,70))
    #arena.plot_percentage_facet(cutoffs=(10,70))
    #arena.plot_pi_facet((10,70))
    #print(arena.plot_percentage_facet())
    #print(arena.summarize(write_to_csvfile=True))   
    #print(arena.summarize_facet(cutoffs=(10)))
    #arena.plot_trackers_y(range_minutes=(0,0),one_plot=True)
        
    #print(arena.get_tracker("R1_0").plot_xy_animated(range_minutes=(10,15),tail_size=1000))

    #arena.get_tracker("R1_1").plot_time_dependent_interactions()
    #arena.get_tracker("R1_1").plot_x()
    #arena.plot_pi(range_minutes=(0,0))
    #arena.plot_transitions_facet()
    #arena.get_tracker("T_1_0").get_x_positions((10,20))
    #print(arena.firstTracker().tracking_region)
    #print(arena.firstTracker().counting_regions)
    #print(arena.first_tracker().PlotXY())
    #print(arena.firstTracker().PlotX())
    #print(arena.firstTracker().PlotY())
    #arena.firstTracker().summarize()
    #arena.test()
