import pandas as pd
import numpy as np 
from . import Tracker
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class PairwiseInteractionTracker(Tracker.Tracker):
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## All of the relevant parameters are defined in the parent class.
        super().__init__(tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata)     
        if(self.rawdata.index.duplicated().any()):                 
            raise ValueError(f"Duplicated frames in {self.name}.")
        
    def set_neighbor(self,neighbor_tracker):
        self.neighbor_tracker = neighbor_tracker
        
        if 'ClosestNeighbor' not in self.rawdata.columns:           
            self.set_neighbor_distance()
        
        self.set_neighbor_quality_and_distance_mm()
        self.update_neighbor_interactions()
           
    def set_neighbor_distance(self):
        ## Check to make sure the short cut will work.
        ## It will only if each row of each tracker has the same frame number.
        ## This might not actually be needed because vector operations are done based on 
        ## index, which I set to frame during initialization.
        #if(sum(self.rawdata['Frame'] - self.neighbor_tracker.rawdata['Frame'])!=0):
        #    raise ValueError(f"Frame mismatch between trackers.")
    
        ## This is the distance between the two trackers at the current time point.
        x1 = self.rawdata['X']
        y1 = self.rawdata['Y']
        x2 = self.neighbor_tracker.rawdata['X']
        y2 = self.neighbor_tracker.rawdata['Y']
        distance = np.sqrt((x1-x2)**2+(y1-y2)**2) 
        self.rawdata['ClosestNeighbor']=distance

    ## This function is called in Arena post processing because it needs access
    ## to other trackers.       
    def set_neighbor_quality_and_distance_mm(self):
        ## This will be a column that is true if the quality of the data is high for both trackers.
        ## This will be used to filter out bad data.
         ## Create a boolean column flagging measures that may not be valid.
        ## If at least one of the two was not found.
        ## Values are High, Low, Indiscrenable, and Not Found.  I don't know whether Low is ever used.
        quality = (self.rawdata['DataQuality']=="High") & (self.neighbor_tracker.rawdata['DataQuality']=="High")
        one_blob = (self.rawdata['NObjects'] + self.neighbor_tracker.rawdata['NObjects']) == 2
        neg_one_distance = (self.rawdata['ClosestNeighbor'] == -1) | (self.neighbor_tracker.rawdata['ClosestNeighbor'] == -1) 
        null_observations = (self.rawdata['ClosestNeighbor'].isnull()) | (self.neighbor_tracker.rawdata['ClosestNeighbor'].isnull())    
           
        final_quality = (quality | one_blob) & (~neg_one_distance) & (~null_observations)
        self.rawdata['IsNeighborValid'] = final_quality 
        
        self.rawdata['ClosestNeighbor_mm'] = self.rawdata['ClosestNeighbor']
        self.rawdata.loc[~self.rawdata['IsNeighborValid'], 'ClosestNeighbor_mm'] = np.nan
        self.rawdata['ClosestNeighbor_mm'] *= self.parameters.mm_per_pixel

    def get_interaction_subset(self, range_minutes):
        if(len(range_minutes)!=2):            
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.interaction_data.copy()
        data_subset = self.interaction_data[(self.interaction_data['Minutes']>=range_minutes[0]) & (self.interaction_data['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

    def get_frames_interacting(self, range_minutes=(0,0)):
        data = self.get_interaction_subset(range_minutes)
        results =[]
        for dist in self.parameters.interaction_distance_mm:
            results.append(data[f'Interaction_{dist}'].sum()) 
        return results
    
    def get_percent_frames_interacting(self, range_minutes=(0,0)):
        data = self.get_interaction_subset(range_minutes)
        results =[]
        for dist in self.parameters.interaction_distance_mm:
            results.append(data[f'Interaction_{dist}'].sum()) 
        total_valid_frames = self.get_total_frames_with_valid_neighbor(range_minutes)
        if(total_valid_frames==0):
            perc_results = [0]*len(results)
        else:
            perc_results=[x/total_valid_frames for x in results]
        return perc_results
    def get_total_frames_with_valid_neighbor(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['IsNeighborValid'].sum()

    def get_mean_neighbor_distance(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['ClosestNeighbor_mm'].mean()

    def get_median_neighbor_distance(self, range_minutes=(0,0)):
        data = self.get_data_subset(range_minutes)
        return data['ClosestNeighbor_mm'].median()

    def is_partner(self, tracker):
        return self.tracking_region_id == tracker.tracking_region_id
    
    def update_neighbor_interactions(self):
        self.interaction_data = self.rawdata.loc[:,['Minutes','Indicator','ClosestNeighbor_mm','IsNeighborValid']]
        for dist in self.parameters.interaction_distance_mm:
            self.interaction_data[f'Interaction_{dist}'] = (self.interaction_data['ClosestNeighbor_mm'] < dist) & (self.interaction_data['IsNeighborValid'])    
      
    def summarize(self, range_minutes=(0,0)):        
        tmp = Tracker.Tracker.summarize(self, range_minutes)
        mean_neighbor_distance = self.get_mean_neighbor_distance(range_minutes)
        median_neighbor_distance = self.get_median_neighbor_distance(range_minutes)
        frames_interacting = self.get_frames_interacting(range_minutes)
        total_valid_frames = self.get_total_frames_with_valid_neighbor(range_minutes)
        if total_valid_frames == 0:
            percent_frames_interacting = [0] * len(frames_interacting)
        else:
            percent_frames_interacting = [x/total_valid_frames for x in frames_interacting]
        
        distance_names = [f"FramesInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]    
        distance_names2 = [f"PercentInteracting_{dist}" for dist in self.parameters.interaction_distance_mm]    
        
        frames_interacting_series = pd.Series(frames_interacting, index=distance_names)
        percent_frames_interacting_series = pd.Series(percent_frames_interacting, index=distance_names2)
        
        result = pd.concat([tmp,pd.Series({'MeanDistance': mean_neighbor_distance}),pd.Series({"MedianDistance" : median_neighbor_distance}),\
            pd.Series({'ValidFrames': total_valid_frames}),frames_interacting_series,percent_frames_interacting_series])

        return result
    
    def get_time_dependent_interactions(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_interaction_subset(range_minutes)
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        interactions =[]

        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            tmp = [start,end,self.get_percent_frames_interacting([start,end])]
            tmp2=[item for sublist in tmp for item in (sublist if isinstance(sublist, list) else [sublist])]
            interactions.append(tmp2)
            
        result = [f'PercentInteractions_{dist}' for dist in self.parameters.interaction_distance_mm]
        result.insert(0,'EndMin')
        result.insert(0,'StartMin')
        return pd.DataFrame(interactions, columns=result)
    
    def get_time_dependent_distances(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data_subset = self.get_data_subset(range_minutes)
        earliest_min = round(data_subset['Minutes'].iat[0])+window_size_min
        latest_min = round(data_subset['Minutes'].iat[-1])        
        results =[]
        for end in range(earliest_min, latest_min + 1, step_size_min):
            start = end - window_size_min
            tmp = self.get_data_subset([start,end])
            results.append([start,end,tmp['ClosestNeighbor_mm'].mean(),tmp['ClosestNeighbor_mm'].median()])
        return pd.DataFrame(results, columns=['StartMin','EndMin','MeanDistance','MedianDistance'])
    
    def plot_time_dependent_distances(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data = self.get_time_dependent_distances(window_size_min,step_size_min,range_minutes)
        plt.figure(figsize=(10, 6))
      
        for column in data.columns:
            if column not in ['StartMin', 'EndMin']:
                plt.plot(data['EndMin'], data[column], marker='o', linestyle='-', label=column)
      
        plt.xlabel('Minutes')
        plt.ylabel('Neighbor Distances (mm)')
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
        plt.legend()      
        plt.grid(True)
        plt.show()
    
    def plot_time_dependent_interactions(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        data = self.get_time_dependent_interactions(window_size_min,step_size_min,range_minutes)
        plt.figure(figsize=(10, 6))
      
        for column in data.columns:
            if column not in ['StartMin', 'EndMin']:
                plt.plot(data['EndMin'], data[column], marker='o', linestyle='-', label=column)
      
        plt.xlabel('Minutes')
        plt.ylabel('Fraction Time Interacting')
        plt.title(f'{self.name} ({self.tracking_region_design["Treatment"].iat[0]})')
        plt.legend()      
        plt.ylim([-0.1,1])
        plt.grid(True)
        plt.show()


    def plot_xy(self, range_minutes=(0,0)):
        """
        Plot the XY positions of the tracked object.

        Parameters:
        range_minutes (tuple): Tuple of two integers specifying the start and end minutes.
        """
        data_subset = self.get_data_subset(range_minutes)
        plt.figure(figsize=(10, 6))
        scatter = plt.scatter(data_subset['Xpos_mm']*(int)(self.tracking_region_design['XLocationMultiplier'].iloc[0]), data_subset['Ypos_mm']*(int)(self.tracking_region_design['YLocationMultiplier'].iloc[0]), c=data_subset['ClosestNeighbor_mm'], cmap='viridis', vmin=data_subset['ClosestNeighbor_mm'].min(), vmax=data_subset['ClosestNeighbor_mm'].max())
        plt.colorbar(scatter, label='Closest Neighbor')
        plt.xlabel('X Position (mm)')
        plt.ylabel('Y Position (mm)')
        title = f'{self.name} ({self.tracking_region_design["Treatment"].iloc[0]})'
        if((int)(self.tracking_region_design['YLocationMultiplier'].iloc[0])==-1 and (int)(self.tracking_region_design['XLocationMultiplier'].iloc[0])==-1):
                title = title + " (X and Y Coordinates Flipped)"
        elif((int)(self.tracking_region_design['YLocationMultiplier'].iloc[0])==-1):
                title = title + " (Y Coordinate Flipped)"
        elif((int)(self.tracking_region_design['XLocationMultiplier'].iloc[0])==-1):
                title = title + " (X Coordinate Flipped)"
        plt.title(title)
        tmp = self.get_plot_limits()
        plt.xlim(tmp[0])
        plt.ylim(tmp[1])
        plt.grid(True)

        if(self.tracking_region_roi['Shape'].values[0]=='Ellipse'):
            ellipse = patches.Ellipse((0, 0), width=self.tracking_region_roi['Width'].values[0]*self.parameters.mm_per_pixel, height=self.tracking_region_roi['Height'].values[0]*self.parameters.mm_per_pixel, edgecolor='gray', facecolor='none', linewidth=1)            
            plt.gca().add_patch(ellipse)

        plt.show()
