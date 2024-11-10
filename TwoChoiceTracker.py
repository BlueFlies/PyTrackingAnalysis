import pandas as pd
import numpy as np
import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class TwoChoiceTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)
        self.verify_experimental_design()
        self.calculate_pi_data()


    def get_pi_subset(self, range_minutes):
        if(len(range_minutes)!=2):            
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.pi_data
        data_subset = self.pi_data[(self.pi_data['Minutes']>=range_minutes[0]) & (self.pi_data['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

    def get_final_pi(self,range_minutes=[0,0]):
        tmp = self.get_cumulative_pi(range_minutes).iloc[-1].at['Cumulative PI']
        return tmp

    def get_cumulative_pi(self,range_minutes=[0,0]):                             
        data_subset = self.get_pi_subset(range_minutes)
        cumpi_n = data_subset['PI'].cumsum()
        cumpi_d= data_subset['PI'].abs().cumsum()
        cumpi = cumpi_n/cumpi_d
        
        data_subset.insert(1, "CumulativePI", cumpi)
        return data_subset
        
    def verify_experimental_design(self):
        if ("ObjectID" not in self.experimental_design.columns):
            raise ValueError(f"Invalid design file for TwoChoiceTracker. Missing column: Object_ID")
        if("TrackingRegion" not in self.experimental_design.columns):
            raise ValueError(f"Invalid design file for TwoChoiceTracker. Missing column: TrackingRegion")
        if("CountingRegion" not in self.experimental_design.columns):
            raise ValueError(f"Invalid design file for TwoChoiceTracker. Missing column: CountingRegion")
        if("Treatment" not in self.experimental_design.columns):
            raise ValueError(f"Invalid design file for TwoChoiceTracker. Missing column: Treatment")
        
        if(self.experimental_design['Treatment'].nunique()!=2):
            raise ValueError(f"Invalid design file for TwoChoiceTracker. Must have exactly two unique treatments.")
        
        if(self.experimental_design.shape[0]!=2):
            raise ValueError(f"Possible invalid design file for TwoChoiceTracker. Should have two treatment rows.")

    def calculate_pi_data(self):
        self.pi_data = self.rawdata.loc[:,['Minutes','Indicator']]
        trt1 = self.rawdata["CountingRegion"] == self.experimental_design['CountingRegion'][0]
        trt2 = self.rawdata["CountingRegion"] == self.experimental_design['CountingRegion'][1]
        pi = trt1.astype(int) - trt2.astype(int)
        
        self.pi_data.insert(1, self.experimental_design['Treatment'][1], trt2)
        self.pi_data.insert(1, self.experimental_design['Treatment'][0], trt1)              
        self.pi_data.insert(1, "PI", pi)

        return

    def plot_cumulative_pi(self, range_minutes=[0,0],show_light=True):
        if(show_light):
            data_subset = self.get_cumulative_pi(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Cumulative PI')
            ax.set_title(f'{self.name}')
            ax.legend()      
            ax.set_ylim([-1,1])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iloc[i]>0:
                ax.axvspan(data_subset['Minutes'].iloc[i], data_subset['Minutes'].iloc[i + 1], color='red', alpha=0.1)
            plt.show()
        else:
            data_subset = self.get_cumulative_pi(range_minutes)
            print(data_subset)
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['CumulativePI'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Cumulative PI')
            plt.title(f'{self.name}')
            plt.legend()      
            plt.ylim([-1,1])
            plt.grid(True)
            plt.show()
            

        
        