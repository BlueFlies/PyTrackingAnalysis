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
    def __init__(self, exp_name, parameters):        
        self.parameters = parameters
        self.experiment_name = exp_name   
        self.summary_data = None
        self.get_experiment_file_info()
        self.get_experimental_design()
        self.create_trackers()
        self.summarize()
        

    def display_head(self, n=5):
        print(self.rawdata.head(n))
        print(self.rawdata.dtypes)


    def get_experiment_file_info(self):
        file_name = self.experiment_name + '.xlsx'
        sheet_name = "ROI"
        
        roi = pd.read_excel(file_name, sheet_name=sheet_name)
        self.tracking_regions =  roi[(roi['Type']=='Tracking')].reset_index(drop=True)
        self.counting_regions =  roi[(roi['Type']=='Counting')].reset_index(drop=True)
       

    def get_experimental_design(self):
        try:
            self.experimental_design = ExperimentalDesign.ExperimentalDesign(self.experiment_name, self.parameters)
        except:            
            self.experimental_design = None

    def read_all_data(self):
        csv_files = natsorted(glob.glob(self.experiment_name + "_Data_*.csv"))
        #Read each CSV file into a DataFrame and store them in a list
        dataframes = [pd.read_csv(file,keep_default_na=False,na_values=['NaN']) for file in csv_files]

        # Concatenate all DataFrames into a single DataFrame
        rd = pd.concat(dataframes, ignore_index=True)
        return rd


    def summarize_facet(self,cutoffs=[10,70]):
        cutoffs.insert(0,0)
        cutoffs.append(float('inf'))
        results = []
        for i in range(len(cutoffs)-1):
            tmp = self.summarize([cutoffs[i],cutoffs[i+1]])
            results.append(tmp)
        all_summaries = pd.concat(results, ignore_index=True)
        return all_summaries

    def summarize(self,range_minutes=[0,0]):
        summaries = []
        for key, tracker in self.trackers.items():
            summary = tracker.summarize(range_minutes)
            summaries.append(summary)
    
        # Concatenate all summaries into a single DataFrame
        all_summaries = pd.DataFrame(summaries)

        self.summary_data = all_summaries        
        return all_summaries
    
    def print_summary(self):
        print(self.summary_data)

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

    def first_tracker(self):
        return self.trackers[self.trackerKeys[0]]

    def get_tracker(self, key):
        return self.trackers.get(key,None)

#region = Treatment plots
    def plot_treatments(self):
        if self.summary_data is None:
            self.summarize()
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_treatments_twochoicetracker()
        else:
            pass
       
    def plot_treatments_facet(self,cutoffs=[10,70]):
        if(self.parameters.tracking_type==Parameters.TrackingType.TWOCHOICETRACKER):
            self.plot_treatments_facet_twochoicetracker()
        else:
            pass

    def plot_treatments_twochoicetracker(self):
        plt.figure(figsize=(10, 6))
        p=sns.stripplot(x='Treatment', y='FinalPI', data=self.summary_data, jitter=True,  hue='Transitions')
        tmp = f"PI Range Minutes = [{self.summary_data["StartMinutes"].min():.2f} , {self.summary_data["EndMinutes"].max():.2f}]" 
        plt.title(tmp)
        plt.xlabel('Treatment')
        plt.ylabel('PI')
        plt.ylim(-1.1,1.1)
        plt.xlim(-.5,1.5)

        df_mean = self.summary_data.groupby('Treatment', sort=False)['FinalPI'].mean()
        ax = plt.gca()
        x_coords = ax.get_xticks()
        counter=0
        for i, y in df_mean.items():
            p.hlines(y, x_coords[counter] - 0.05, x_coords[counter] + 0.05, color='red', zorder=2)
            counter+=1
        plt.show()

    def plot_treatments_facet_twochoicetracker(self, cutoffs=[10,70]):
        if self.summary_data is None:
            print("Summary data is not available.")
            return
        
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
            plt.xlim(-.5,1.5)

        # Create the FacetGrid
        g = sns.FacetGrid(the_data, col='StartMinutes', col_wrap=3, height=4)
        #g.map(sns.stripplot, 'Treatment', 'FinalPI', 'Transitions', jitter=True)
        g.map_dataframe(custom_plot)
        # Add titles and labels
        g.set_titles(col_template="Start: {col_name:.2f}min")
        g.set_axis_labels('Treatment', 'PI')
        g.set(ylim=(-1.1, 1.1))
        
        plt.show()


#end region

    def run_pairwise_comparisons(self, column='FinalPI', range_minutes=[0,0]):
        summary = self.summarize(range_minutes)
        if 'Treatment' not in summary.columns:
            raise ValueError("The summary data does not contain a 'Treatment' column.")
        if column not in summary.columns:
            raise ValueError(f"The summary data does not contain a '{column}' column.")
        
        # Perform pairwise t-tests
        tukey = pairwise_tukeyhsd(endog=summary[column], groups=summary['Treatment'], alpha=0.05)
        print(f"Column = {column}, Range Minutes = [{range_minutes[0]:.2f} , {range_minutes[1]:.2f}] ")
        print(tukey)
    
    def test(self):
        print(self.firstTracker().locations())


if __name__ == "__main__":
    p=Parameters.Parameters()
    #p.set_small_arena_values(Parameters.TrackingType.TWOCHOICETRACKER)
    p.set_movie_values(Parameters.TrackingType.TWOCHOICETRACKER, 10, 0.056)
    arena = Arena('MaxIRSetup',p)
    arena.run_pairwise_comparisons(range_minutes=[10,70])
    #arena.plot_treatments()
    #print(arena.plot_treatments_facet_twochoicetracker([30,60]))
    #print(arena.summarize([0,30]))
    
    #print(arena.get_tracker("T_0_0").plot_xy([10,20]))
    #arena.get_tracker("T_1_0").plot_pis()
    #print(arena.firstTracker().tracking_region)
    #print(arena.firstTracker().counting_regions)
    #print(arena.first_tracker().PlotXY())
    #print(arena.firstTracker().PlotX())
    #print(arena.firstTracker().PlotY())
    #arena.firstTracker().summarize()
    #arena.test()
