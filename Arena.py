import numpy as np
import pandas as pd
import Tracker 
import Counter
import TwoChoiceTracker
import TwoChoiceCounter
import PairwiseInteractionTracker
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

class Arena:

#region ########### Initialization Functions ############
    def __init__(self, exp_name, parameters, data_path='./', force_preprocessing=False):        
        self.parameters = parameters
        self.experiment_name = exp_name   
        self.data_path = data_path      
        self.get_experiment_file_info()
        self.get_experimental_design()
        self.create_trackers(force_preprocessing)   
        self.computed_summaries={}     

    def get_experiment_file_info(self):
        file_name = self.data_path + self.experiment_name + '.xlsx'
        sheet_name = "ROI"
        
        roi = pd.read_excel(file_name, sheet_name=sheet_name)
        self.tracking_regions =  roi[(roi['Type']=='Tracking')].reset_index(drop=True)
        self.counting_regions =  roi[(roi['Type']=='Counting')].reset_index(drop=True)
     
    def get_experimental_design(self):        
        try:            
            self.experimental_design = ExperimentalDesign.ExperimentalDesign(self.data_path+self.experiment_name, self.parameters)                           
        except:            
            self.experimental_design = None

    def read_all_data(self):
        csv_files = natsorted(glob.glob(self.data_path+self.experiment_name + "_Data_*.csv"))
        #Read each CSV file into a DataFrame and store them in a list
        dataframes = [pd.read_csv(file,keep_default_na=False,na_values=['NaN']) for file in csv_files]

        # Concatenate all DataFrames into a single DataFrame
        rd = pd.concat(dataframes, ignore_index=True)
        return rd
    
    def create_trackers(self, force_preprocessing):
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
                else:
                    raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be an instance of TrackingType enum.")
                tmp_trackers[f'{region}'] = counter 
            self.trackers = OrderedDict((key, tmp_trackers[key]) for key in natsorted(tmp_trackers))
        else:
            raise ValueError(f"Invalid tracking class: {self.parameters.get_tracking_class()}. Must be an instance of TrackingClass enum.")
        self.check_for_postprocessing(rawdata) 

    def check_for_postprocessing(self,rawdata):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):             
            for key, tracker in self.trackers.items():
                for key2, tracker2 in self.trackers.items():
                    if(key!=key2 and tracker.get_tracking_region_id()==tracker2.get_tracking_region_id()):
                        tracker.set_neighbor(tracker2)
        
    def check_for_preprocessing(self,rawdata, force_preprocessing=False):
        ## For now we will disable this.  It should be only used if the post-processing fails
        ## because the data for partner trackers does not line up.
        if ((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) and force_preprocessing):             
            if 'ClosestNeighbor' not in rawdata.columns:
                rawdata=self.calculate_distances_for_pairwise_tracker(rawdata)
        return rawdata
    
    def calculate_distances_for_pairwise_tracker(self,rawdata):
        ## This works but it's pretty slow.
        # Group the data by 'TrackingRegion', 'ObjectID', and 'Frame'
        print("Calculating pairwise distances will take a while...")
        grouped_data = rawdata.groupby(['Frame', 'TrackingRegion'])
        
        distances = []
        
        for (frame, region), group in grouped_data:
            if len(group) == 2:
                x1, y1 = group.iloc[0][['X', 'Y']]
                x2, y2 = group.iloc[1][['X', 'Y']]
                distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                distances.extend([distance, distance])  # Add the distance for both observations
            elif group['NObjhects'].sum() == 2:
                distance = 0
                distances.extend([distance, distance])  # Add the distance for both observations
            else:
                print("Yuck")
                distances.extend([np.nan] * len(group))  # Add NaN for groups that don't have exactly 2 observations

        rawdata['CalcDistance'] = distances
        return rawdata
        
#endregion ########### Initialization Functions ############
    
    
#region ########### Access Functions ############
    
    def first_tracker(self):
        tmp = list(self.trackers.keys())
        return self.trackers[tmp[0]]

    def get_tracker(self, key):
        return self.trackers.get(key,None)

#endregion ########### Access Functions ############

#region ########### Basic Computation Functions ############
    def summarize_facet(self,cutoffs=(10,70),copy_to_clipboard=False, write_to_csvfile=False, remove_partners=False):
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
            all_summaries.to_clipboard(index=False)
        if(write_to_csvfile==True):            
            all_summaries.to_csv(f"{self.data_path+self.experiment_name}_Summary_Facet.csv",index=False)      
        return all_summaries

    def summarize(self,range_minutes=(0,0),copy_to_clipboard=False, write_to_csvfile=False, remove_partners=False):
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
            all_summaries.to_clipboard(index=False)
        if(write_to_csvfile==True):            
            all_summaries.to_csv(f"{self.data_path+self.experiment_name}_Summary.csv",index=False) 
        return all_summaries
    
#endregion ########### Basic Computation Functions ############

#region ########### User Plotting Functions ############
    def plot_pi(self, range_minutes=(0,0)):      
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_pi_facet(self,cutoffs=(10,70)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_percentage(self, range_minutes=(0,0)):      
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")  
    def plot_percentage_facet(self,cutoffs=(10,70)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    def plot_totaldistance(self, range_minutes=(0,0)):      
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        else:
            pass
    def plot_totaldistance_facet(self,cutoffs=(10,70)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        else:
            pass

    def plot_trackers_percentages(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_percentages(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    
    def plot_trackers_pis(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_pis(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")

    def plot_trackers_x(self,range_minutes=(0,0),one_plot=False):
        if(one_plot):
            for treatment in self.experimental_design.tracking_regions['Treatment'].unique():        
                fig, ax = plt.subplots(figsize=(10, 6))
            
                # Generate a colormap
                colormap = plt.cm.get_cmap('tab10', len(self.trackers))
                
                for idx, (key, tracker) in enumerate(self.trackers.items()):
                    if(tracker.get_treatment()==treatment):
                        # Assuming tracker has a method to get x-positions within the specified range
                        x_positions = tracker.get_x_positions(range_minutes)
                        ax.plot(x_positions, label=key, color=colormap(idx),alpha=0.7)
                
                ax.set_xlabel('Minutes')
                ax.set_ylabel('X Position')
                title = treatment + " (Axis flips applied if specified)"
                ax.set_title(title)            
                plt.show()            
        else:            
            if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
                for key, tracker in self.trackers.items():
                    tracker.plot_x(range_minutes)
            elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):         
                for key, tracker in self.trackers.items():
                    tracker.plot_x(range_minutes)
            else:
                raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")

    def plot_trackers_y(self,range_minutes=(0,0),one_plot=False):
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
            if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
                for key, tracker in self.trackers.items():
                    tracker.plot_y(range_minutes)
            elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):         
                for key, tracker in self.trackers.items():
                    tracker.plot_y(range_minutes)
            else:
                raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")

    def plot_trackers_xy(self,range_minutes=(0,0)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.TRACKER):         
            for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
        elif(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):         
            for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    
    def plot_trackers_time_dependent_interactions(self,window_size_min=10,step_size_min=5,range_minutes=(0,0)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            last_region = None
            for key, tracker in self.trackers.items():
                if(tracker.tracking_region_id!=last_region):
                    tracker.plot_time_dependent_interactions(window_size_min,step_size_min,range_minutes)
                    last_region = tracker.tracking_region_id
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a PairwiseInteractionTracker.")
   
    def plot_transitions(self,range_minutes=(0,0)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
  
    def plot_interactions(self,range_minutes=(0,0)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_interactions_pairwiseinteractiontracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
      
    def plot_interactions_facet(self,cutoffs=(10,70)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER):
            self.plot_interactions_facet_pairwiseinteractiontracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
        
    def plot_transitions_facet(self,cutoffs=(10,70)):
        if(self.parameters.get_tracking_type()==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.get_tracking_type()}. Must be a TwoChoiceTracker.")
    
#endregion ########### User Plotting Functions ############


#region ########### Backend Plotting ############
    def plot_pi_twochoicetracker(self, range_minutes=(0,0)):
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
    
    def plot_transitions_twochoicetracker(self, range_minutes=(0,0)):
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

    def plot_transitions_facet_twochoicetracker(self, cutoffs=(10,70)):   
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
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Transitions (transitions/min)')        
        
        plt.show()

    def plot_percentage_twochoicetracker(self, range_minutes=(0,0)):
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
        
    def plot_interactions_pairwiseinteractiontracker(self, range_minutes=(0,0)):
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

    def plot_totaldistance_generaltracker(self, range_minutes=(0,0)):
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
        g = sns.FacetGrid(the_data, col='FacetRange', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Facet Range (min): {col_name}")
        g.set_axis_labels('Treatment', 'Distance (mm/min)')        
        
        plt.show()

#endregion ########### Backend Plotting ############

#region ########### Statistical Functions ############
    def run_pairwise_comparisons(self, metric='FinalPI', range_minutes=(0,0)):
        if((self.parameters.get_tracking_type()==Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER) and ("Interacting" in metric)):
            remove_partners=True
        summary = self.summarize(range_minutes, remove_partners=remove_partners)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        # Perform pairwise t-tests
        treatments = summary['Treatment'].unique()

        print(treatments)
        if(len(treatments)<2):
            raise ValueError("There must be at least two treatments to compare.")
        elif(len(treatments)==2):
            group1 = summary[summary['Treatment'] == treatments[0]][metric]
            group2 = summary[summary['Treatment'] == treatments[1]][metric]
            t_stat, p_value = ttest_ind(group1, group2)
            print("############# T-Test #############")
            print(f"Column = {metric}, Range Minutes = ({range_minutes[0]:.2f} , {range_minutes[1]:.2f}) ")
            print(f"{treatments[0]} vs. {treatments[1]}: T={t_stat:.2f}, p={p_value:.5f}")
        else:
            tukey = pairwise_tukeyhsd(endog=summary[metric], groups=summary['Treatment'], alpha=0.05)            
            print(f"Column = {metric}, Range Minutes = [{range_minutes[0]:.2f} , {range_minutes[1]:.2f}] ")
            print(tukey)
    
    def run_pairwise_comparisons_facet(self, metric='FinalPI', cutoffs=(10,70), remove_partners=False):
        summary = self.summarize_facet(cutoffs, remove_partners=remove_partners)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        for frange in summary['FacetRange'].unique():
            subset = summary[summary['FacetRange'] == frange]
            treatments = subset['Treatment'].unique()
            if(len(treatments)<2):
                raise ValueError("There must be at least two treatments to compare.")
            elif(len(treatments)==2):
                group1 = subset[subset['Treatment'] == treatments[0]][metric]
                group2 = subset[subset['Treatment'] == treatments[1]][metric]
                t_stat, p_value = ttest_ind(group1, group2)
                print("############# T-Test #############")
                print(f"Column = {metric}, Range Minutes = ({frange[0]:.2f} , {frange[1]:.2f}) ")
                print(f"{treatments[0]} vs. {treatments[1]}: T={t_stat:.2f}, p={p_value:.5f}")
                print("\n")
            else:              
                tukey = pairwise_tukeyhsd(endog=subset[metric], groups=subset['Treatment'], alpha=0.05)
                print(f"Column = {metric}, Facet Range = ({frange[0]:.2f},{frange[1]:.2f})")
                print(tukey)
                print("\n")
            
#endregion ########### Statistical Functions ############        


if __name__ == "__main__":
    p=Parameters.Parameters()
    #p.set_small_arena_values(Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER)
    p.set_pairwise_interaction_values_arena_max([2,4,8])
    #p.set_movie_values(Parameters.TrackingType.TWOCHOICETRACKER, 10, 0.056)
    #p.set_arena_max_values(Parameters.TrackingType.TWOCHOICETRACKER)         
    arena = Arena('MaxxxPWI_FLIR',p,"./Data/")
    #print(arena.first_tracker().rawdata[['ClosestNeighbor','IsNeighborValid']].head(30))
    #arena.first_tracker().plot_cumulative_percentage(range_minutes=(0,0),show_light=True)
    #print(arena.summarize(remove_partners=True))
    #arena.summarize_facet(cutoffs=(10,70),remove_partners=True)
    #arena.plot_trackers_time_dependent_interactions()
    #print(arena.first_tracker().plot_time_dependent_distances())
    #arena.run_pairwise_comparisons_facet(cutoffs=(10,70))
    #arena.plot_percentage_facet(cutoffs=(10,70))
    #arena.plot_pi_facet((10,70))
    #print(arena.plot_percentage_facet())
    #print(arena.summarize())
    #print(arena.summarize_facet(cutoffs=(10)))
    #arena.plot_trackers_y(range_minutes=(0,0),one_plot=True)
        
    #print(arena.get_tracker("R1_0").plot_xy_animated(range_minutes=(10,15),tail_size=1000))

    arena.get_tracker("R1_1").plot_time_dependent_interactions()
    arena.get_tracker("R1_1").plot_x()
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
