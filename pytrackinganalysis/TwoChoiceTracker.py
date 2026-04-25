import pandas as pd
import numpy as np 
from . import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)                
        self.calculate_pi_data()      

    def get_pi_subset(self, range_minutes):
        if(len(range_minutes)!=2):            
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.pi_data.copy()
        data_subset = self.pi_data[(self.pi_data['Minutes']>=range_minutes[0]) & (self.pi_data['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

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
        rle_results = self.rle(range_minutes)
        rle_results = rle_results[rle_results['values'] != "None"]

        changes = rle_results['values'].ne(rle_results['values'].shift())

        ## TODO: Maybe make sure the transitions happen only between counting regions that 
        ## should be part of this 
        return sum(changes)-1

    def get_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_pi([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','PI'])
    
    def get_time_dependent_percentage(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_percentage([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','Percentage'])
    
    def get_counting_region_counts(self,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)               
        keys = list(self.counting_regions_design.keys())
        return data_subset.loc[:,keys[0]:keys[1]].sum()

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
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        try:
            final_pi = self.get_final_pi(range_minutes)
        except:
            final_pi = pd.NA
        try:
            final_perc = self.get_final_percentage(range_minutes)
        except:
            final_perc = pd.NA
        try:
            transitions = self.get_transitions(range_minutes)
            transitions_min=transitions/tmp['ObsMinutes']
        except:
            transitions = pd.NA
            transitions_min=pd.NA
        try:
            counts = self.get_counting_region_counts(range_minutes)
        except:
            counts = pd.NA
      
        result = pd.concat([tmp,pd.Series({'FinalPI': final_pi}),pd.Series({"FinalPercentage" : final_perc}),counts,pd.Series({'Transitions': transitions}),pd.Series({'TransitionsPerMin': transitions_min})])

        return result
    
    #region ########### QC Functions ############
    

    #endregion ########### QC Functions ############  