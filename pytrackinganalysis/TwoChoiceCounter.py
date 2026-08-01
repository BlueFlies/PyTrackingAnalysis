import pandas as pd
import numpy as np 
from . import Counter
from . import windowing
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceCounter(Counter.Counter):
    def __init__(self, tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)                
        self.calculate_pi_data()    

    def get_pi_subset(self, range_minutes):
        """Per-minute PI rows within ``[start, end)``; ``(0, 0)`` means the whole recording."""
        return windowing.slice_by_minutes(self.pi_data, range_minutes)

    def summarize(self, range_minutes=(0,0)):        
        tmp = Counter.Counter.summarize(self, range_minutes)
        final_pi = self.get_final_pi(range_minutes)
        final_perc = self.get_final_percentage(range_minutes)
        counts = self.get_counting_region_counts(range_minutes)
        result = pd.concat([tmp,pd.Series({'FinalPI': final_pi}),pd.Series({"FinalPercentage" : final_perc}),counts])
        return result
    
    def get_final_pi(self,range_minutes=(0,0)):
        tmp = self.get_cumulative_pi(range_minutes).iloc[-1].at['CumulativePI']
        return tmp
    
    def get_cumulative_pi(self,range_minutes=(0,0)):                             
        data_subset = self.get_pi_subset(range_minutes)
        
        keys = list(self.counting_regions_design.keys())
        a = data_subset[keys[0]].cumsum()
        b= data_subset[keys[1]].cumsum()
        cumpi = ((a - b)/(a + b)).replace([np.inf, -np.inf], np.nan)

        data_subset.insert(1, "CumulativePI", cumpi)
        return data_subset

    def calculate_pi_data(self):
        self.pi_data = self.sum_counts_assign_treatments()

        trts =[]
        for key, value in self.counting_regions_design.items():
            trts.append(self.pi_data[key])

        a = trts[0].astype(int)
        b = trts[1].astype(int)
        pi = ((a - b)/(a + b)).replace([np.inf, -np.inf], np.nan)
        perc = (a/(a + b)).replace([np.inf, -np.inf], np.nan)

        self.pi_data.insert(1, "Percentage", perc)
        self.pi_data.insert(1, "PI", pi)      
        return
    
    def get_counting_region_counts(self,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        ## Select the canonical group columns by name — a positional slice would
        ## silently pick up any column that happened to sit between them.
        keys = list(self.counting_regions_design.keys())
        return data_subset[keys].sum()

    def get_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        if(len(data_subset)==0):
            return pd.DataFrame(columns=['StartMin','EndMin','PI'])
        earliest_min = round(data_subset['Minutes'].iloc[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iloc[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_pi([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','PI'])
    
    def get_final_percentage(self,range_minutes=(0,0)):
        tmp = self.get_cumulative_percentage(range_minutes).iloc[-1].at['CumulativePercentage']
        return tmp
    
    def get_time_dependent_percentage(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        if(len(data_subset)==0):
            return pd.DataFrame(columns=['StartMin','EndMin','Percentage'])
        earliest_min = round(data_subset['Minutes'].iloc[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iloc[-1])        
        pis =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            pis.append([start,end,self.get_final_percentage([start,end])])
            
        return pd.DataFrame(pis, columns=['StartMin','EndMin','Percentage'])
    
    def get_cumulative_percentage(self,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
        keys = list(self.counting_regions_design.keys())
        a = data_subset[keys[0]].cumsum()
        b= data_subset[keys[1]].cumsum()
        cumperc = (a/(a + b)).replace([np.inf, -np.inf], np.nan)
        
        data_subset.insert(1, "CumulativePercentage", cumperc)
        return data_subset    
 
    def sum_counts_assign_treatments(self):
        """Per-minute counts per counting region, aggregated into the canonical groups.

        Every alias of a group contributes to that group's total. Summing (rather
        than assigning) matters whenever more than one alias of the same group is
        occupied in the same minute — assigning would keep only the last alias
        seen and discard the rest.
        """
        # Group the data by 'Minutes' and 'CountingRegion' and count the number of rows in each group
        counts = self.rawdata.groupby(['Minutes', 'CountingRegion']).size().reset_index(name='Count')

        # Pivot the table to have 'Minutes' as rows and 'CountingRegion' as columns
        pivot_table = counts.pivot(index='Minutes', columns='CountingRegion', values='Count').fillna(0)
        pivot_table.reset_index(inplace=True)
        pivot_table.columns.name = None
        avg_indicator = self.rawdata.groupby('Minutes')['Indicator'].mean().reset_index()
        pivot_table['Indicator'] = avg_indicator['Indicator']

        for key, aliases in self.counting_regions_design.items():
            ## A raw region column named after the group itself would be shadowed
            ## by the aggregate, so move it aside before building the aggregate.
            if key in pivot_table.columns:
                pivot_table.rename(columns={key: f"{key}_CountingRegion"}, inplace=True)

            alias_columns = []
            for alias in aliases:
                column = f"{alias}_CountingRegion" if alias == key else alias
                if column in pivot_table.columns and column not in alias_columns:
                    alias_columns.append(column)

            # No alias was ever visited — the group is legitimately empty.
            pivot_table[key] = pivot_table[alias_columns].sum(axis=1) if alias_columns else 0
        return pivot_table
    
    def plot_cumulative_pi(self, range_minutes=(0,0),show_light=False):
        if(show_light):
            data_subset = self.get_cumulative_pi(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Cumulative PI')
            ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
            ax.legend()      
            ax.set_ylim([-1,1])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iloc[i]>0:
                ax.axvspan(data_subset['Minutes'].iloc[i], data_subset['Minutes'].iloc[i + 1], color='red', alpha=0.01)
            plt.show()
        else:
            data_subset = self.get_cumulative_pi(range_minutes)            
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Cumulative PI')
            plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
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
            ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
            ax.legend()      
            ax.set_ylim([-0.05,1.05])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iloc[i]>0:
                ax.axvspan(data_subset['Minutes'].iloc[i], data_subset['Minutes'].iloc[i + 1], color='red', alpha=0.01)
            plt.show()
        else:
            data_subset = self.get_cumulative_percentage(range_minutes)            
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['CumulativePercentage'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Cumulative Percentage')
            plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
            plt.legend()      
            plt.ylim([-0.05,1.05])
            plt.grid(True)
            plt.show()
            
    def plot_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        data = self.get_time_dependent_pi(window_size_min,step_size_min,range_minutes)
        plt.figure(figsize=(10, 6))
        plt.plot(data['EndMin'], data['PI'], marker='o', linestyle='-',label=self.name)
        plt.xlabel('Minutes')
        plt.ylabel('PI')
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
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
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
        plt.legend()      
        plt.ylim([-0.05,1.05])
        plt.grid(True)
        plt.show()
        
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
        ax.set_title(f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})')
        ax.legend()
        ax.set_ylim([-0.05, 1.05])
        ax.grid(True)
        
        if show_light:
            for i in range(len(cumulative_data) - 1):
                if cumulative_data['Indicator'].iloc[i] > 0:
                    ax.axvspan(cumulative_data['Minutes'].iloc[i], cumulative_data['Minutes'].iloc[i + 1], color='red', alpha=0.01)
        
        plt.show()  