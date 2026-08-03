import pandas as pd
import numpy as np 
from . import Tracker
from . import ExperimentalDesign
from . import windowing
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)                
        self.calculate_pi_data()      

    def get_pi_subset(self, range_minutes):
        """Per-frame PI rows within ``[start, end)``; ``(0, 0)`` means the whole recording."""
        return windowing.slice_by_minutes(self.pi_data, range_minutes)

    def rle(self, range_minutes=(0,0)):
        rd = self.get_data_subset(range_minutes)
        # Ensure the series is of type string
        series = rd['CountingRegion'].astype(str)
        
        # Identify changes in the series values
        changes = series.ne(series.shift())
        
        # Get the run lengths and values
        run_lengths = series.groupby(changes.cumsum()).size()
        run_values = series.groupby(changes.cumsum()).first()
        
        # Combine run lengths and values into a DataFrame
        rle_df = pd.DataFrame({'lengths': run_lengths, 'values': run_values}).reset_index(drop=True)
        
        return rle_df

    def get_transitions(self, range_minutes=(0,0)):
        """Count alternations between the two counting *groups* in the window.

        Out-of-region runs ("None") are dropped rather than treated as a third
        state, so a brief excursion outside both regions does not break a visit
        into two.

        The comparison is made on the group, not the raw cell: those cells hold
        region *aliases* (``Light, LL, L``), so moving from "L" to "LL" — the
        same group under two spellings — used to be counted as a transition.
        """
        rle_results = self.rle(range_minutes)
        region_to_group = ExperimentalDesign.alias_to_group_map(self.counting_regions_design)
        groups = rle_results['values'].map(region_to_group)
        groups = groups[groups.notna()]
        if(len(groups)==0):
            ## No visits to any counting region — "zero transitions" would be a
            ## claim we cannot make from an empty window.
            return pd.NA

        changes = groups.ne(groups.shift())
        return int(changes.sum()) - 1

    def get_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        if(len(data_subset)==0):
            return pd.DataFrame(columns=['StartMin','EndMin','PI'])
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_pi([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','PI'])
    
    def get_time_dependent_percentage(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        if(len(data_subset)==0):
            return pd.DataFrame(columns=['StartMin','EndMin','Percentage'])
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_percentage([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','Percentage'])
    
    def get_counting_region_counts(self,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        ## Select the canonical group columns by name — a positional slice would
        ## silently pick up any column that happened to sit between them.
        keys = list(self.counting_regions_design.keys())
        return data_subset[keys].sum()

    def get_final_pi(self,range_minutes=(0,0)):
        tmp = self.get_cumulative_pi(range_minutes).iloc[-1].at['CumulativePI']
        return tmp
    
    def get_final_percentage(self,range_minutes=(0,0)):
        tmp = self.get_cumulative_percentage(range_minutes).iloc[-1].at['CumulativePercentage']
        return tmp

    def get_cumulative_pi(self,range_minutes=(0,0)):                             
        data_subset = self.get_pi_subset(range_minutes)
        cumpi_n = data_subset['PI'].cumsum()
        cumpi_d= data_subset['PI'].abs().cumsum()
        cumpi = (cumpi_n/cumpi_d).replace([np.inf, -np.inf], np.nan)
        
        data_subset.insert(1, "CumulativePI", cumpi)
        return data_subset
        
    def get_cumulative_percentage(self,range_minutes=(0,0)):                             
        data_subset = self.get_pi_subset(range_minutes)
        cumperc_n = data_subset['Percentage'].cumsum() 
        cumperc_d = list(range(1,data_subset.shape[0]+1))
        cumperc = cumperc_n/cumperc_d
        
        data_subset.insert(1, "CumulativePercentage", cumperc)
        return data_subset

    def calculate_pi_data(self):        
        if self.counting_regions_design is None or not isinstance(self.counting_regions_design, dict):
            raise ValueError(
                "TwoChoiceTracker requires a design file with [Counting Regions]. "
                f"Design file may be missing or failed to load for experiment. "
                f"Tracker: {self.name}"
            )
        self.pi_data = self.rawdata.loc[:,['Minutes','Indicator']]
        
        trts = []
        for key, value in self.counting_regions_design.items():        
            trts.append(self.rawdata["CountingRegion"].isin(value))
            
        pi = trts[0].astype(int) - trts[1].astype(int)
        
        perc = trts[0].astype(int)
        
        keys = list(self.counting_regions_design.keys())
        self.pi_data.insert(1, keys[1], trts[1])
        self.pi_data.insert(1, keys[0], trts[0])              
        self.pi_data.insert(1, "Percentage", perc)
        self.pi_data.insert(1, "PI", pi)        
        return

    def plot_pis(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        
        cumulative_data = self.get_cumulative_pi(range_minutes)
        
        # Get time-dependent PI data
        time_dependent_data = self.get_time_dependent_pi(window_size_min, step_size_min, range_minutes)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Plot cumulative PI
        ax.plot(cumulative_data['Minutes'], cumulative_data['CumulativePI'], label='Cumulative PI', linestyle='-', color='blue')
        
        # Plot time-dependent PI
        ax.plot(time_dependent_data['EndMin'], time_dependent_data['PI'], marker='o', linestyle='--', label='Time-Dependent PI', color='green')
        
        ax.set_xlabel('Minutes')
        ax.set_ylabel('PI')
        ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
        ax.legend()
        ax.set_ylim([-1, 1])
        ax.grid(True)
        
        if show_light:
            for i in range(len(cumulative_data) - 1):
                if cumulative_data['Indicator'].iloc[i] > 0:
                    ax.axvspan(cumulative_data['Minutes'].iloc[i], cumulative_data['Minutes'].iloc[i + 1], color='red', alpha=0.1)
        
        plt.show()       

    def plot_percentages(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        
        cumulative_data = self.get_cumulative_percentage(range_minutes)
        
        # Get time-dependent PI data
        time_dependent_data = self.get_time_dependent_percentage(window_size_min, step_size_min, range_minutes)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Plot cumulative PI
        ax.plot(cumulative_data['Minutes'], cumulative_data['CumulativePercentage'], label='Cumulative Percentage', linestyle='-', color='blue')
        
        # Plot time-dependent PI
        ax.plot(time_dependent_data['EndMin'], time_dependent_data['Percentage'], marker='o', linestyle='--', label='Time-Dependent Percentage', color='green')
        
        ax.set_xlabel('Minutes')
        ax.set_ylabel('Percentage')
        ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
        ax.legend()
        ax.set_ylim([-0.05, 1.05])
        ax.grid(True)
        
        if show_light:
            for i in range(len(cumulative_data) - 1):
                if cumulative_data['Indicator'].iloc[i] > 0:
                    ax.axvspan(cumulative_data['Minutes'].iloc[i], cumulative_data['Minutes'].iloc[i + 1], color='red', alpha=0.01)
        
        plt.show()       

    def plot_cumulative_pi(self, range_minutes=(0,0),show_light=False):
        if(show_light):
            data_subset = self.get_cumulative_pi(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Cumulative PI')
            ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
            ax.legend()      
            ax.set_ylim([-1,1])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iat[i]>0:
                ax.axvspan(data_subset['Minutes'].iat[i], data_subset['Minutes'].iat[i + 1], color='red', alpha=0.01)
            plt.show()
        else:
            data_subset = self.get_cumulative_pi(range_minutes)            
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Cumulative PI')
            plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
            plt.legend()      
            plt.ylim([-1,1])
            plt.grid(True)
            plt.show()
            
    def plot_cumulative_percentage(self, range_minutes=(0,0),show_light=False):
        if(show_light):
            data_subset = self.get_cumulative_percentage(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['CumulativePercentage'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Cumulative Percentage')
            ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
            ax.legend()      
            ax.set_ylim([-0.05,1.05])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iat[i]>0:
                ax.axvspan(data_subset['Minutes'].iat[i], data_subset['Minutes'].iat[i + 1], color='red', alpha=0.01)
            plt.show()
        else:
            data_subset = self.get_cumulative_percentage(range_minutes)            
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['CumulativePercentage'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Cumulative Percentage')
            plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
            plt.legend()      
            plt.ylim([-0.05,1.05])
            plt.grid(True)
            plt.show()
            
    def plot_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data = self.get_time_dependent_pi(window_size_min,step_size_min,range_minutes)
        plt.figure(figsize=(10, 6))
        plt.plot(data['EndMin'], data['PI'], marker='o', linestyle='-',label=self.name)
        plt.xlabel('Minutes')
        plt.ylabel('PI')
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
        plt.legend()      
        plt.ylim([-1,1])
        plt.grid(True)
        plt.show()

    def plot_time_dependent_percentage(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        data = self.get_time_dependent_percentage(window_size_min,step_size_min,range_minutes)
        plt.figure(figsize=(10, 6))
        plt.plot(data['EndMin'], data['Percentage'], marker='o', linestyle='-',label=self.name)
        plt.xlabel('Minutes')
        plt.ylabel('Percentage')
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
        plt.legend()      
        plt.ylim([-0.05,1.05])
        plt.grid(True)
        plt.show()
    
    def summarize(self, range_minutes=(0,0)):
        """Summary row for this tracker over ``range_minutes``.

        An empty window reports NA for every choice metric. Anything else that
        goes wrong is allowed to propagate with the tracker and window attached,
        rather than being flattened into a plausible-looking NA — a silent NA
        here is indistinguishable from a legitimately missing measurement.
        """
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        pi_subset = self.get_pi_subset(range_minutes)
        ## Counts come back as a zero-filled Series even for an empty window,
        ## which keeps the column set identical across facets.
        counts = self.get_counting_region_counts(range_minutes)

        if len(pi_subset) == 0:
            final_pi = pd.NA
            final_perc = pd.NA
            transitions = pd.NA
            transitions_min = pd.NA
        else:
            try:
                final_pi = self.get_final_pi(range_minutes)
                final_perc = self.get_final_percentage(range_minutes)
                transitions = self.get_transitions(range_minutes)
            except (KeyError, IndexError, ValueError) as err:
                raise ValueError(
                    f"{self.name}: could not summarize choice metrics for range {tuple(range_minutes)}: {err}"
                ) from err
            transitions_min = windowing.safe_rate(transitions, tmp['ObsMinutes'])

        result = pd.concat([tmp,pd.Series({'FinalPI': final_pi}),pd.Series({"FinalPercentage" : final_perc}),counts,pd.Series({'Transitions': transitions}),pd.Series({'TransitionsPerMin': transitions_min})])

        return result
    
    #region ########### QC Functions ############
    

    #endregion ########### QC Functions ############  