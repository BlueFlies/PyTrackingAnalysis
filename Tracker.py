import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation

class Tracker:
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        ## These are the key identifiers for the tracker.  They are defined by the data file.
        self.tracking_region_id = tracking_region_id
        self.object_id = object_id
        ## Contact the two identifying features into a unique name for the tracking blob.
        self.name = f'{tracking_region_id}_{object_id}'
        self.rawdata = rawdata        
        self.rawdata.reset_index(drop=True, inplace=True)
        self.parameters =parameters        

        ## Now to get the information from the experiment design file (new format).  This is used in the summary function and 
        ## will likely be used in all stats like functions that combine replicates within a treatment group.
        if(exp_design is not None):            
            self.tracking_region_design = exp_design.get_tracking_region(self.tracking_region_id)
            self.counting_regions_design = exp_design.get_counting_regions(self.rawdata['CountingRegion'].unique()).reset_index(drop=True)
        else:
            self.tracking_region_design = None
            self.counting_regions_design = None
        
        ## These are the ROI from the experiment file.  They are used for plotting and presumably for centrophobism stuff.
        self.tracking_region_roi = tracking_regions[tracking_regions['Name']==tracking_region_id].reset_index(drop=True)        
        self.counting_regions_roi = counting_regions

        ## These functions should come after all the parameters are set.        
        self.calculate_minutes()
        self.calculate_speeds_and_feeds()

    def calculate_minutes(self):
        if(self.parameters.fps==-1):
            fulltime = pd.to_datetime(self.rawdata['Time'])+pd.to_timedelta(self.rawdata['Millisec'],unit='ms')
            timediff = fulltime.diff().dt.total_seconds().copy()
            timediff.iat[0]=0   
            self.rawdata['Minutes']= timediff.cumsum()/60            
        elif (self.parameters.fps==0):
            self.rawdata['Minutes'] = self.rawdata['MSec']/(1000*60)                      
        else:
            ## If there is a defined FPS we will use it directly with the frame number.
            ## Can't trust the MSec column so we will base time on frames.           
            self.rawdata['Minutes'] = self.rawdata['Frame']/(self.parameters.fps*60)
        return

    def calculate_speeds_and_feeds(self):
        self.rawdata['Xpos_mm'] = self.rawdata['RelX']*self.parameters.mm_per_pixel
        self.rawdata['Ypos_mm'] = self.rawdata['RelY']*self.parameters.mm_per_pixel
        deltax = self.rawdata['Xpos_mm'].diff() 
        deltay = self.rawdata['Ypos_mm'].diff()
        deltax[0]=0
        deltay[0]=0
        self.rawdata['Dist_mm'] = (deltax**2 + deltay**2)**0.5
        self.rawdata['DeltaSec'] = self.rawdata['Minutes'].copy().diff() * 60
        self.rawdata.loc[0,'DeltaSec']=0
        window_size = int(round(1/self.rawdata['DeltaSec'].mean(),0) * self.parameters.speed_window_seconds)
        if(window_size<=1):
            self.rawdata['Speed_mm_s'] = self.rawdata['Dist_mm']/self.rawdata['DeltaSec']
        else:
            self.rawdata['DistWindow_mm']  = self.rawdata['Dist_mm'].rolling(window=window_size).sum()
            self.rawdata.loc[0,'DistWindow_mm']=0
            self.rawdata['DeltaSecWindow'] = self.rawdata['DeltaSec'].rolling(window=window_size).sum()
            self.rawdata.loc[0,'DeltaSecWindow']=0
            self.rawdata['Speed_mm_sec']  = self.rawdata['DistWindow_mm']/self.rawdata['DeltaSecWindow']
            self.rawdata.loc[0,'Speed_mm_sec']=0

        self.rawdata['IsWalking'] = self.rawdata['Speed_mm_sec'] > self.parameters.walking_speed_mm_sec
        self.rawdata['IsMicroMove'] = (self.rawdata['Speed_mm_sec'] > self.parameters.micro_move_speed_mm_sec[0]) & (self.rawdata['Speed_mm_sec'] < self.parameters.micro_move_speed_mm_sec[1])
        self.rawdata['IsResting'] = True
        ## Resting is not walking or micro move but can be altered by sleep.
        self.rawdata.loc[self.rawdata['IsWalking']==True,'IsResting'] = False
        self.rawdata.loc[self.rawdata['IsMicroMove']==True,'IsResting'] = False
        
        self.calculate_sleeping()
        
    ## This is definitely beta code at the moment. But it may be working reasonably well. It requires a good value for the lower bound of micro move speed.
    def calculate_sleeping(self):
        self.rawdata['IsSleeping'] = False
        runs = self.calculate_run_boundaries() 
        for i,run in runs.iterrows():
            if(run['IsSleeping']):
                self.rawdata.loc[run['start']:run['end'],'IsResting'] = False
                self.rawdata.loc[run['start']:run['end'],'IsSleeping'] = True

    def calculate_run_boundaries(self):
        # Ensure the series is boolean
        series=self.rawdata['IsResting'].copy()
    
        # Identify where the value changes
        change_points = series.diff().fillna(0).astype(bool)
    
        # Create a group identifier for each run
        run_id = change_points.cumsum()
    
        # Group by the run identifier and calculate the start and end indices
        run_boundaries = series.groupby(run_id).apply(lambda x: (x.index[0], x.index[-1], x.iloc[0])).reset_index(drop=True)
        run_boundaries.columns = ['start', 'end', 'value']
        run_boundaries = pd.DataFrame(run_boundaries.tolist(),columns=['start','end','value'])

        run_boundaries['EndMin'] = self.rawdata.loc[run_boundaries['end'], 'Minutes'].reset_index(drop=True)
        run_boundaries['StartMin'] = self.rawdata.loc[run_boundaries['start'], 'Minutes'].reset_index(drop=True)
        run_boundaries['DurationMin'] = run_boundaries['EndMin'] - run_boundaries['StartMin']
        run_boundaries['IsSleeping'] = (run_boundaries['DurationMin']>=self.parameters.sleep_threshold_min) & run_boundaries['value']==True
        
        return run_boundaries

    def get_data_subset(self, range_minutes):
        if(len(range_minutes)!=2):
            raise ValueError(f"Invalid range_minutes: {range_minutes}. Must be a list of two integers.")
        if(sum(range_minutes)==0):
            return self.rawdata
        data_subset = self.rawdata[(self.rawdata['Minutes']>=range_minutes[0]) & (self.rawdata['Minutes']<=range_minutes[1])]
        data_subset.reset_index(drop=True, inplace=True)
        return data_subset

    def summarize(self, range_minutes=[0,0]):
        data_subset = self.get_data_subset(range_minutes)
        
        perc_sleeping = data_subset['IsSleeping'].sum()/len(data_subset)
        perc_walking = data_subset['IsWalking'].sum()/len(data_subset)
        perc_micro = data_subset['IsMicroMove'].sum()/len(data_subset)
        perc_resting = data_subset['IsResting'].sum()/len(data_subset)

        avg_speed = data_subset['Speed_mm_sec'].mean()
        total_distance = data_subset['Dist_mm'].sum()
        lastrow = data_subset.shape[0]-1
        obs_minutes = data_subset.at[lastrow,'Minutes'] - data_subset.at[0,'Minutes']
        start_minutes = data_subset.at[0,'Minutes']
        end_minutes = data_subset.at[lastrow,'Minutes']

        if(self.tracking_region_design is not None):
            treatment = self.tracking_region_design['Treatment'].iloc[0]

        total_distance_dtrack = (data_subset.at[lastrow,'TotalDistance'] - data_subset.at[0,'TotalDistance'])*self.parameters.mm_per_pixel
        tmp = (f"Treatment: {treatment}, Name: {self.name}, ObsMin: {obs_minutes:.2f}, Sleeping: {perc_sleeping:.2f}, Walking: {perc_walking:.2f}, Micro: {perc_micro:.2f}, Resting: {perc_resting:.2f}, AvgSpeed: {avg_speed:.2f}, TotalDist: {total_distance:.2f}, TotalDist2: {total_distance_dtrack:.2f}, StartMin: {start_minutes:.2f}, EndMin: {end_minutes:.2f}")
        result = pd.Series([treatment, self.name,self.tracking_region_id,self.object_id,obs_minutes,total_distance,total_distance_dtrack,perc_sleeping,perc_walking,perc_micro,perc_resting,avg_speed,start_minutes,end_minutes])
        result.index = ['Treatment','Name','TrackingRegion','ObjectID','ObsMinutes','TotalDistance','TotalDistanceDTrack','PercSleeping','PercWalking','PercMicro','PercResting','AvgSpeed','StartMinutes','EndMinutes']
        return result

    def get_plot_limits(self):
        xlims=(self.tracking_region_roi['Width'].values[0]*self.parameters.mm_per_pixel)/(-2.0),(self.tracking_region_roi['Width'].values[0]*self.parameters.mm_per_pixel)/(2.0)
        ylims=(self.tracking_region_roi['Height'].values[0]*self.parameters.mm_per_pixel)/(-2.0),(self.tracking_region_roi['Height'].values[0]*self.parameters.mm_per_pixel)/(2.0)
        return xlims,ylims
        
    def plot_x(self, range_minutes=[0,0], show_light=False):
        if(show_light):
            data_subset = self.get_data_subset(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['Xpos_mm'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Position (mm)')
            ax.set_title(f'{self.name}')
            ax.legend()      
            tmp = self.get_plot_limits()        
            ax.set_ylim(tmp[0])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iloc[i]>0:
                ax.axvspan(data_subset['Minutes'].iloc[i], data_subset['Minutes'].iloc[i + 1], color='red', alpha=0.1)
            plt.show()
        else:
            data_subset = self.get_data_subset(range_minutes)
            plt.figure(figsize=(10, 6))
            plt.plot(data_subset['Minutes'], data_subset['Xpos_mm'], label=self.name)
            plt.xlabel('Minutes')
            plt.ylabel('Position (mm)')
            plt.title(f'{self.name}')
            plt.legend()
            tmp = self.get_plot_limits()        
            plt.ylim(tmp[0])
            plt.grid(True)
            plt.show()

    def plot_y(self, range_minutes=[0,0], show_light=False):
        if(show_light):
            data_subset = self.get_data_subset(range_minutes)            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(data_subset['Minutes'], data_subset['Ypos_mm'], label=self.name)
            ax.set_xlabel('Minutes')
            ax.set_ylabel('Position (mm)')
            ax.set_title(f'{self.name}')
            ax.legend()      
            tmp = self.get_plot_limits()        
            ax.set_ylim(tmp[1])
            ax.grid(True)

            for i in range(len(data_subset) - 1):
              if data_subset['Indicator'].iloc[i]>0:
                ax.axvspan(data_subset['Minutes'].iloc[i], data_subset['Minutes'].iloc[i + 1], color='red', alpha=0.1)
            plt.show()
        else:
            data_subset = self.get_data_subset(range_minutes)
            plt.figure(figsize=(10, 6))        
            plt.plot(data_subset['Minutes'], data_subset['Ypos_mm'], label='Y Position (mm)')
            plt.xlabel('Minutes')
            plt.ylabel('Position (mm)')
            plt.title(f'{self.name}')
            plt.legend()
            tmp = self.get_plot_limits()
            plt.ylim(tmp[1])
            plt.grid(True)
            plt.show()

    def plot_xy(self, range_minutes=[0,0]):
        data_subset = self.get_data_subset(range_minutes)
        plt.figure(figsize=(10, 6))
        scatter = plt.scatter(data_subset['Xpos_mm'], data_subset['Ypos_mm'], c=data_subset['Minutes'], cmap='viridis', vmin=data_subset['Minutes'].min(), vmax=data_subset['Minutes'].max())
        plt.colorbar(scatter, label='Minutes')
        plt.xlabel('X Position (mm)')
        plt.ylabel('Y Position (mm)')
        plt.title(f'{self.name}')
        tmp = self.get_plot_limits()
        plt.xlim(tmp[0])
        plt.ylim(tmp[1])
        plt.grid(True)

        if(self.tracking_region_roi['Shape'].values[0]=='Ellipse'):
            ellipse = patches.Ellipse((0, 0), width=self.tracking_region_roi['Width'].values[0]*self.parameters.mm_per_pixel, height=self.tracking_region_roi['Height'].values[0]*self.parameters.mm_per_pixel, edgecolor='gray', facecolor='none', linewidth=1)            
            plt.gca().add_patch(ellipse)

        plt.show()

    def plot_xy_animated(self, range_minutes=[0, 0], interval = .1):
        data_subset = self.get_data_subset(range_minutes)

        fig, ax = plt.subplots(figsize=(10, 6))
        scatter = ax.scatter([], [], c=[], cmap='viridis', vmin=data_subset['Minutes'].min(), vmax=data_subset['Minutes'].max())
        colorbar = plt.colorbar(scatter, ax=ax, label='Minutes')
        ax.set_xlabel('X Position (mm)')
        ax.set_ylabel('Y Position (mm)')
        ax.set_title(f'{self.name}')
        xlims, ylims = self.get_plot_limits()
        ax.set_xlim(xlims)
        ax.set_ylim(ylims)
        ax.grid(True)

        if self.tracking_region_roi['Shape'].values[0] == 'Ellipse':
            ellipse = patches.Ellipse((0, 0), width=self.tracking_region_roi['Width'].values[0] * self.parameters.mm_per_pixel, height=self.tracking_region_roi['Height'].values[0] * self.parameters.mm_per_pixel, edgecolor='gray', facecolor='none', linewidth=1)
            ax.add_patch(ellipse)

        time_text = ax.text(0.02, 0.95, '', transform=ax.transAxes)

        def init():
            scatter.set_offsets([np.nan, np.nan])
            scatter.set_array([])
            time_text.set_text('')
            return scatter,time_text

        def update(frame):
            current_data = data_subset.iloc[:frame + 1]            
            scatter.set_offsets(np.c_[current_data['Xpos_mm'], current_data['Ypos_mm']])
            scatter.set_array(current_data['Minutes'])
            time_text.set_text(f"Minutes: {current_data['Minutes'].iloc[-1]:.2f}")
            return scatter, time_text

        ani = FuncAnimation(fig, update, frames=len(data_subset), init_func=init, blit=True, repeat=False, interval=interval)
        plt.show()



    def __str__(self):
        #return f"a={self.rawdata['CountingRegion']}"
        #return f"Tracker(name={self.name}, fps={self.parameters.fps}, head=\n{self.rawdata.head()},tail=\n{self.rawdata.tail()})"
        tmp = self.summarize()
        tmp_str = (f"Name: {tmp['Name']}, ObsMin: {tmp['ObsMinutes']:.2f}, TotalDist: {tmp['TotalDistance']:.2f}, TotalDist2: {tmp['TotalDistanceDTrack']:.2f}, Sleeping: {tmp['PercSleeping']:.2f}, Walking: {tmp['PercWalking']:.2f}, Micro: {tmp['PercMicro']:.2f}, Resting: {tmp['PercResting']:.2f}, AvgSpeed: {tmp['AvgSpeed']:.2f}, StartMin: {tmp['StartMinutes']:.2f}, EndMin: {tmp['EndMinutes']:.2f}")
        return tmp_str