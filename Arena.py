import numpy as np
import pandas as pd
import Tracker 
import TwoChoiceTracker
import Parameters
import ExperimentalDesign
import glob
from natsort import natsorted
import seaborn as sns
import matplotlib.pyplot as plt
from statsmodels.stats.multicomp import pairwise_tukeyhsd

class Arena:

#region ########### Initialization Functions ############
    def __init__(self, exp_name, parameters, data_path='./'):        
        self.parameters = parameters
        self.experiment_name = exp_name   
        self.data_path = data_path      
        self.get_experiment_file_info()
        self.get_experimental_design()
        self.create_trackers()   
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
    def create_trackers(self):
        rawdata = self.read_all_data()
        self.trackers = {}
        grouped_data = rawdata.groupby(['TrackingRegion','ObjectID'] )
        for (region,object_id), group in grouped_data:
            if(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
                tracker = Tracker.Tracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            elif(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
                tracker = TwoChoiceTracker.TwoChoiceTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            else:
                raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be an instance of TrackingType enum.")
            self.trackers[f'{region}_{object_id}'] = tracker 
        self.trackerKeys = list(self.trackers.keys())

#endregion ########### Initialization Functions ############
    
    
#region ########### Access Functions ############
    
    def first_tracker(self):
        return self.trackers[self.trackerKeys[0]]

    def get_tracker(self, key):
        return self.trackers.get(key,None)

#endregion ########### Access Functions ############

#region ########### Basic Computation Functions ############
    def summarize_facet(self,cutoffs=(10,70),copy_to_clipboard=False, write_to_csvfile=False):
        cutoffs = list(cutoffs)
        cutoffs.insert(0,0)
        cutoffs.append(float('inf'))
        results = []
        for i in range(len(cutoffs)-1):
            tmp = self.summarize(tuple([cutoffs[i],cutoffs[i+1]]))
            results.append(tmp)
        all_summaries = pd.concat(results, ignore_index=True)
        if(copy_to_clipboard):            
            all_summaries.to_clipboard(index=False)
        if(write_to_csvfile==True):            
            all_summaries.to_csv(f"{self.data_path+self.experiment_name}_Summary_Facet.csv",index=False)      
        return all_summaries

    def summarize(self,range_minutes=(0,0),copy_to_clipboard=False, write_to_csvfile=False):
        if( range_minutes in self.computed_summaries):
            return self.computed_summaries[range_minutes]
        
        summaries = []
        for key, tracker in self.trackers.items():
            summary = tracker.summarize(range_minutes)
            summaries.append(summary)
    
        # Concatenate all summaries into a single DataFrame
        all_summaries = pd.DataFrame(summaries)
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
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_twochoicetracker()
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_pi_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_facet_twochoicetracker()
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_percentage(self, range_minutes=(0,0)):      
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_twochoicetracker()
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")  
    def plot_percentage_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_facet_twochoicetracker()
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_totaldistance(self, range_minutes=(0,0)):      
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_generaltracker()
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_generaltracker()
        else:
            pass
    def plot_totaldistance_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_facet_generaltracker()
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_facet_generaltracker()
        else:
            pass

    def plot_trackers_percentages(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_percentages(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    
    def plot_trackers_pis(self,window_size_min=10,step_size_min=5,range_minutes=(0,0), show_light=False):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_pis(window_size_min,step_size_min,range_minutes,show_light)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")

    def plot_trackers_x(self,range_minutes=(0,0)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_x(range_minutes)
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):         
            for key, tracker in self.trackers.items():
                tracker.plot_x(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")

    def plot_trackers_xy(self,range_minutes=(0,0)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):         
            for key, tracker in self.trackers.items():
                tracker.plot_xy(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
                
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
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='StartMinutes', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Start: {col_name:.2f}min")
        g.set_axis_labels('Treatment', 'PI')
        g.set(ylim=(-1.1, 1.1))
        
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
            plt.xlim(-.5,ntreatments-1+0.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='StartMinutes', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Start: {col_name:.2f}min")
        g.set_axis_labels('Treatment', 'Percentage')
        g.set(ylim=(-.05, 1.05))
        
        plt.show()

    def plot_totaldistance_generaltracker(self, range_minutes=(0,0)):
        summary_data = self.summarize(range_minutes)
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='TotalDistancePerMin', data=summary_data, jitter=True,  hue='Transitions')
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
        plt.show()

    def plot_totaldistance_facet_generaltracker(self, cutoffs=(10,70)):   
        # Create a new column for the minute ranges
        the_data = self.summarize_facet(cutoffs)

        def custom_plot(data, **kwargs):
            p=sns.stripplot(x='Treatment', y='TotalDistancePerMin', hue='Transitions', data=data, jitter=True, **kwargs)
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
        g = sns.FacetGrid(the_data, col='StartMinutes', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Start: {col_name:.2f}min")
        g.set_axis_labels('Treatment', 'Distance (mm/min)')        
        
        plt.show()

#endregion ########### Backend Plotting ############

#region ########### Statistical Functions ############
    def run_pairwise_comparisons(self, metric='FinalPI', range_minutes=(0,0)):
        summary = self.summarize(range_minutes)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        # Perform pairwise t-tests
        tukey = pairwise_tukeyhsd(endog=summary[metric], groups=summary['Treatment'], alpha=0.05)
        print(f"Column = {metric}, Range Minutes = [{range_minutes[0]:.2f} , {range_minutes[1]:.2f}] ")
        print(tukey)
    
    def run_pairwise_comparisons_facet(self, metric='FinalPI', cutoffs=(10,70)):
        summary = self.summarize_facet(cutoffs)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if metric not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{metric}' column.")
        
        for start_minute in summary['StartMinutes'].unique():
            subset = summary[summary['StartMinutes'] == start_minute]
            if len(subset['Treatment'].unique()) > 1:  # Ensure there are at least two treatments to compare
                tukey = pairwise_tukeyhsd(endog=subset[metric], groups=subset['Treatment'], alpha=0.05)
                print(f"Column = {metric}, Start Minutes = {start_minute:.2f}")
                print(tukey)
                print("\n")
            else:
                print(f"Not enough treatments to compare for Start Minutes = {start_minute:.2f}")

#endregion ########### Statistical Functions ############        


if __name__ == "__main__":
    p=Parameters.Parameters()
    #p.set_small_arena_values(Parameters.TrackingType.TWOCHOICETRACKER)
    #p.set_movie_values(Parameters.TrackingType.TWOCHOICETRACKER, 10, 0.056)
    p.set_arena_max_values(Parameters.TrackingType.TWOCHOICETRACKER)
    p.print()
    arena = Arena('MaxIRSetup',p,"./Data/")
    arena.run_pairwise_comparisons_facet(cutoffs=(10,70))
    #arena.plot_totaldistance_facet(cutoffs=(10,70))
    #print(arena.plot_percentage_facet())
    #print(arena.summarize(write_to_csvfile=True))
        
    #print(arena.get_tracker("T_0_0").plot_percentages(range_minutes=(10,30)))
    #arena.plot_pi(range_minutes=(0,0))
    #arena.plot_pi(range_minutes=(0,0))
    #arena.get_tracker("T_1_0").plot_pis()
    #print(arena.firstTracker().tracking_region)
    #print(arena.firstTracker().counting_regions)
    #print(arena.first_tracker().PlotXY())
    #print(arena.firstTracker().PlotX())
    #print(arena.firstTracker().PlotY())
    #arena.firstTracker().summarize()
    #arena.test()
