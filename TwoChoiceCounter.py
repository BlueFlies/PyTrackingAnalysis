import pandas as pd
import numpy as np 
import Counter
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceCounter(Counter.Counter):
    def __init__(self, tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)                
        self.calculate_pi_data()    

    def get_pi_subset(self, range_minutes):
        if(len(range_minutes)!=2):            
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.pi_data.copy()
        data_subset = self.pi_data[(self.pi_data['Minutes']>=range_minutes[0]) & (self.pi_data['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

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
        cumpi = (a - b)/(a + b)
        
        data_subset.insert(1, "CumulativePI", cumpi)
        return data_subset
    
    def calculate_pi_data(self):        
        self.pi_data = self.sum_counts_assign_treatments()
        
        trts =[]
        for key, value in self.counting_regions_design.items():
            trts.append(self.pi_data[key])
        
        pi = (trts[0].astype(int) - trts[1].astype(int))/(trts[0].astype(int) + trts[1].astype(int))
        perc = trts[0].astype(int)/(trts[0].astype(int) + trts[1].astype(int))

        self.pi_data.insert(1, "Percentage", perc)
        self.pi_data.insert(1, "PI", pi)      
        return
   
    def get_time_dependent_pi(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_pi_subset(range_minutes)
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
        cumperc = (a)/(a + b)
        
        data_subset.insert(1, "CumulativePercentage", cumperc)
        return data_subset    
 
    def sum_counts_assign_treatments(self):
        # Group the data by 'Minutes' and 'CountingRegion' and count the number of rows in each group
        counts = self.rawdata.groupby(['Minutes', 'CountingRegion']).size().reset_index(name='Count')
        
        # Pivot the table to have 'Minutes' as rows and 'CountingRegion' as columns
        pivot_table = counts.pivot(index='Minutes', columns='CountingRegion', values='Count').fillna(0)
        pivot_table.reset_index(inplace=True)
        pivot_table.columns.name = None
        avg_indicator = self.rawdata.groupby('Minutes')['Indicator'].mean().reset_index()
        pivot_table['Indicator'] = avg_indicator['Indicator']
        for key, value in self.counting_regions_design.items():
            for column in pivot_table.columns:
                if column in value:
                    if(column==key):
                        pivot_table["tmp"] = pivot_table[column]
                        newname = column +"_CountingRegion"
                        pivot_table.rename(columns={column: newname}, inplace=True)
                        pivot_table.rename(columns={"tmp": key}, inplace=True)
                    else:
                        pivot_table[key] = pivot_table[column]
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