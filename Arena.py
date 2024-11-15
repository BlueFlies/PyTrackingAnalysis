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
from collections import OrderedDict
from scipy.stats import ttest_ind

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
        tmp_trackers = {}
        grouped_data = rawdata.groupby(['TrackingRegion','ObjectID'] )
        for (region,object_id), group in grouped_data:
            if(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
                tracker = Tracker.Tracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            elif(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
                tracker = TwoChoiceTracker.TwoChoiceTracker(region,object_id,self.tracking_regions,self.counting_regions,self.parameters,self.experimental_design,group)
            else:
                raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be an instance of TrackingType enum.")
            tmp_trackers[f'{region}_{object_id}'] = tracker 
        self.trackers = OrderedDict((key, tmp_trackers[key]) for key in natsorted(tmp_trackers))


#endregion ########### Initialization Functions ############
    
    
#region ########### Access Functions ############
    
    def first_tracker(self):
        tmp = list(self.trackers.keys())
        return self.trackers[tmp[0]]

    def get_tracker(self, key):
        return self.trackers.get(key,None)

#endregion ########### Access Functions ############

#region ########### Basic Computation Functions ############
    def summarize_facet(self,cutoffs=(10,70),copy_to_clipboard=False, write_to_csvfile=False):
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
            tmp = self.summarize(tuple([cutoffs[i],cutoffs[i+1]]))
            tmp['FacetRange']=[tuple([cutoffs[i],cutoffs[i+1]])]*len(tmp)
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
            self.plot_pi_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_pi_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_pi_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_percentage(self, range_minutes=(0,0)):      
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")  
    def plot_percentage_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_percentage_facet_twochoicetracker(cutoffs)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
    def plot_totaldistance(self, range_minutes=(0,0)):      
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_generaltracker(range_minutes)
        else:
            pass
    def plot_totaldistance_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
        elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):
            self.plot_totaldistance_facet_generaltracker(cutoffs)
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
            if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
                for key, tracker in self.trackers.items():
                    tracker.plot_x(range_minutes)
            elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):         
                for key, tracker in self.trackers.items():
                    tracker.plot_x(range_minutes)
            else:
                raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")

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
            if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
                for key, tracker in self.trackers.items():
                    tracker.plot_y(range_minutes)
            elif(self.parameters.tracking_type==Parameters.TrackingType.TRACKER):         
                for key, tracker in self.trackers.items():
                    tracker.plot_y(range_minutes)
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
    
    def plot_transitions(self,range_minutes=(0,0)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_twochoicetracker(range_minutes)
        else:
            raise ValueError(f"Invalid tracking type: {self.parameters.tracking_type}. Must be a TwoChoiceTracker.")
        
    def plot_transitions_facet(self,cutoffs=(10,70)):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_transitions_facet_twochoicetracker(cutoffs)
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
        tmp = list(self.experimental_design.counting_regions.keys())             
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
        summary = self.summarize(range_minutes)
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
    
    def run_pairwise_comparisons_facet(self, metric='FinalPI', cutoffs=(10,70)):
        summary = self.summarize_facet(cutoffs)
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
    #p.set_small_arena_values(Parameters.TrackingType.TWOCHOICETRACKER)
    #p.set_movie_values(Parameters.TrackingType.TWOCHOICETRACKER, 10, 0.056)
    p.set_arena_max_values(Parameters.TrackingType.TWOCHOICETRACKER)       
    arena = Arena('MaxIRSetup',p,"./Data/")
    #arena.run_pairwise_comparisons_facet(cutoffs=(10,70))
    #arena.plot_percentage_facet(cutoffs=(10,70))
    #arena.plot_pi_facet((10,70))
    #print(arena.plot_percentage_facet())
    #print(arena.summarize_facet(cutoffs=(10)))
    #arena.plot_trackers_y(range_minutes=(0,0),one_plot=True)
        
    print(arena.get_tracker("T_1_0").plot_xy_animated(range_minutes=(10,15),tail_size=1000))
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
