import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

class Tracker:
    def __init__(self, tracking_region_id, object_id, tracking_regions, counting_regions, parameters, exp_design,rawdata):
        self.rawdata = rawdata        
        self.object_id = object_id
        self.rawdata.reset_index(drop=True, inplace=True)
        self.parameters =parameters
        self.experimental_design = exp_design
        self.name = f'{tracking_region_id}_{object_id}'
        self.tracking_region = tracking_regions[tracking_regions['Name']==tracking_region_id].reset_index(drop=True)
        self.counting_regions = counting_regions
        self.calculate_minutes()
        self.calculate_speeds_and_feeds()

    def calculate_minutes(self):
        if(self.parameters.fps==-1):
            fulltime = pd.to_datetime(self.rawdata['Time'])+pd.to_timedelta(self.rawdata['Millisec'],unit='ms')
            timediff = fulltime.diff().dt.total_seconds().copy()
            timediff[0]=0   
            self.rawdata['Minutes']= timediff.cumsum()/60            
        elif (self.parameters.fps==0):
            self.rawdata['Minutes'] = self.rawdata['MSec']/(1000*60)                      
        else:
            mmin = (1.0/self.parameters.fps*60)
            self.rawdata['Minutes'] = pd.Series(np.arange(0,mmin*len(self.rawdata['MSec'],mmin)))
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
        
    ## This is definitely beta code at the moment.
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
        total_distance_dtrack = (data_subset.at[lastrow,'TotalDistance'] - data_subset.at[0,'TotalDistance'])*self.parameters.mm_per_pixel
        tmp = (f"Name: {self.name}, ObsMin: {obs_minutes:.2f}, Sleeping: {perc_sleeping:.2f}, Walking: {perc_walking:.2f}, Micro: {perc_micro:.2f}, Resting: {perc_resting:.2f}, AvgSpeed: {avg_speed:.2f}, TotalDist: {total_distance:.2f}, TotalDist2: {total_distance_dtrack:.2f}, StartMin: {start_minutes:.2f}, EndMin: {end_minutes:.2f}")
        result = pd.Series([self.name,self.tracking_region,self.object_id,obs_minutes,total_distance,total_distance_dtrack,perc_sleeping,perc_walking,perc_micro,perc_resting,avg_speed,start_minutes,end_minutes])
        result.index = ['Name','TrackingRegion','ObjectID','ObsMinutes','TotalDistance','TotalDistanceDTrack','PercSleeping','PercWalking','PercMicro','PercResting','AvgSpeed','StartMinutes','EndMinutes']
        return result

    def get_plot_limits(self):
        xlims=(self.tracking_region['Width'].values[0]*self.parameters.mm_per_pixel)/(-2.0),(self.tracking_region['Width'].values[0]*self.parameters.mm_per_pixel)/(2.0)
        ylims=(self.tracking_region['Height'].values[0]*self.parameters.mm_per_pixel)/(-2.0),(self.tracking_region['Height'].values[0]*self.parameters.mm_per_pixel)/(2.0)
        return xlims,ylims
        
    def PlotX(self):
        plt.figure(figsize=(10, 6))
        plt.plot(self.rawdata['Minutes'], self.rawdata['Xpos_mm'], label='X Position (mm)')
        plt.xlabel('Minutes')
        plt.ylabel('Position (mm)')
        plt.title(f'{self.name}')
        plt.legend()
        tmp = self.get_plot_limits()        
        plt.ylim(tmp[0])
        plt.grid(True)
        plt.show()
    
    def PlotY(self):
        plt.figure(figsize=(10, 6))        
        plt.plot(self.rawdata['Minutes'], self.rawdata['Ypos_mm'], label='Y Position (mm)')
        plt.xlabel('Minutes')
        plt.ylabel('Position (mm)')
        plt.title(f'{self.name}')
        plt.legend()
        tmp = self.get_plot_limits()
        plt.ylim(tmp[1])
        plt.grid(True)
        plt.show()

    def PlotXY(self):
        plt.figure(figsize=(10, 6))
        scatter = plt.scatter(self.rawdata['Xpos_mm'], self.rawdata['Ypos_mm'], c=self.rawdata['Minutes'], cmap='viridis')
        plt.colorbar(scatter, label='Minutes')
        plt.xlabel('X Position (mm)')
        plt.ylabel('Y Position (mm)')
        plt.title(f'{self.name}')
        tmp = self.get_plot_limits()
        plt.xlim(tmp[0])
        plt.ylim(tmp[1])
        plt.grid(True)

        if(self.tracking_region['Shape'].values[0]=='Rectangle'):
            ellipse = patches.Ellipse((0, 0), width=self.tracking_region['Width'].values[0]*self.parameters.mm_per_pixel, height=self.tracking_region['Height'].values[0]*self.parameters.mm_per_pixel, edgecolor='gray', facecolor='none', linewidth=1)            
            plt.gca().add_patch(ellipse)

        plt.show()

    def __str__(self):
        #return f"a={self.rawdata['CountingRegion']}"
        #return f"Tracker(name={self.name}, fps={self.parameters.fps}, head=\n{self.rawdata.head()},tail=\n{self.rawdata.tail()})"
        tmp = self.summarize()
        tmp_str = (f"Name: {tmp['Name']}, ObsMin: {tmp['ObsMinutes']:.2f}, TotalDist: {tmp['TotalDistance']:.2f}, TotalDist2: {tmp['TotalDistanceDTrack']:.2f}, Sleeping: {tmp['PercSleeping']:.2f}, Walking: {tmp['PercWalking']:.2f}, Micro: {tmp['PercMicro']:.2f}, Resting: {tmp['PercResting']:.2f}, AvgSpeed: {tmp['AvgSpeed']:.2f}, StartMin: {tmp['StartMinutes']:.2f}, EndMin: {tmp['EndMinutes']:.2f}")
        return tmp_str