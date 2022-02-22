# -*- coding: utf-8 -*-
"""
BDTools V2.0
@Liyao Zhang
Start Date 1/10/2022
End Date 2/22/2022

TO-DO:
    0.I/O
    -支持csv/gdb文件图层读取
    1.空间可视化模块
    -(✔)加载深圳市天地图
    -(✔)点转为100x100网格
    -(✔)加载mapbox底图
    -(✔)图例样式修改
    -(✔)创建用户定义可视化参数界面（标题、底图、网格大小、颜色、数值范围、k、断点方式、透明度等）
    -(进行中)根据数据类型和实际需求出不同图（样方密度/饼状图/核密度/OD图）
    -增加POI分析（核密度）
    2.建立空间数据库，上传范围后实时加载调用范围内数据
"""
import pandas as pd
import geopandas as gpd
import numpy as np
import xlsxwriter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import mapclassify as mc
from gooey import Gooey, GooeyParser
from GCS_Conversion import gcj2wgs
from shapely.geometry import Point, Polygon
import cartopy.io.img_tiles as cimgt
import cartopy.crs as ccrs

# MapBox底图
class MB_vec(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        #'sk.eyJ1IjoianVkZDE0N3QiLCJhIjoiY2t6b3g5bzJnMGh3ZTJvcW13NWZ5ZWhieSJ9.oJ8Vr-ttT0S5gA3uquL2LA' https://api.mapbox.com/styles/v1/mapbox/light-v10/tiles
        access_token = 'pk.eyJ1IjoianVkZDE0N3QiLCJhIjoiY2t6b3d4cjJsM2NuOTJxbnJsaXBrandobyJ9.VXx0tjmrPmujViEjYFgMqg'
        url = (f'https://api.mapbox.com/styles/v1/judd147t/ckzqqirua00nu14l980idnr9s/tiles/256'
               f'/{z}/{x}/{y}?access_token={access_token}'.format(z=z, y=y, x=x, token=access_token))
        return url
# 天地图底图
class TDT_vec(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        key = 'abc457154134c560ff8e160e0c509be5'
        url = 'http://t0.tianditu.gov.cn/DataServer?T=vec_w&x=%s&y=%s&l=%s&tk=%s' % (x, y, z, key)
        return url
plt.rcParams["font.family"] = "SimHei"

@Gooey(program_name="BDTools",
       default_size=(680, 830),
       tabbed_groups=True,
       clear_before_run=True,
       navigation='Tabbed',
       language='Chinese',
       menu=[{
        'name': '帮助',
        'items': [{
                'type': 'AboutDialog',
                'menuTitle': '关于',
                'name': 'BDTools',
                'description': '一款便捷处理百度平台大数据的应用',
                'version': '2.0',
                'copyright': '2022',
                'developer': '张力铫，黄智徽，萧俊瑶',
                'license': '深圳市蕾奥规划设计咨询股份有限公司'
            }, {
                'type': 'Link',
                'menuTitle': '使用说明',
                'url': 'https://shimo.im/docs/QQtwcVtXtgvGW6TY'
            }]
    }]
)
def main():
    parser = GooeyParser()
    # *** 界面搭建及参数获取 *** #
    #可视化参数
    group_vis = parser.add_argument_group('可视化设置', '选择默认参数或自定义参数', gooey_options={"columns": 2})
    group_vis.add_argument('-title', metavar='图片标题', widget="TextField", default='无标题')
    group_vis.add_argument('-basemap', metavar='底图样式', choices=['Mapbox','天地图'], default='Mapbox')
    group_vis.add_argument('-cellsize', metavar='网格大小', help='单位:米', choices=['100','200','500','1000'], default='100')
    #FIXME 添加palettable颜色
    group_vis.add_argument('-cmap', metavar='色调', choices=['Greys','Reds','Oranges','OrRd','YlOrRd','YlOrBr','YlGnBu','hot','Spectral'], default='OrRd')
    group_vis.add_argument('-vmin', metavar='最小值', help='取值范围', widget="Slider", default=1)
    group_vis.add_argument('-k', metavar='数据分层数', widget="Slider", default=5)
    #FIXME 添加用户自定义断点
    group_vis.add_argument('-scheme', metavar='断点方式', choices=['equal_interval','fisher_jenks','headtail_breaks','jenks_caspall','natural_breaks','quantiles','user_defined'], default='natural_breaks')
    group_vis.add_argument('-alpha', metavar='透明度', help='0-1之间', widget="DecimalField", default=1)
    
    #shp转excel
    group0 = parser.add_argument_group('shp转excel', '可用于申请范围内整体画像、通勤方式等含比例数据', gooey_options={"columns": 1})
    group0.add_argument('-geo', metavar='shp文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group0.add_argument('-out', metavar='结果文件夹保存路径', widget="DirChooser", nargs='?')
    
    #客流数量
    group1 = parser.add_argument_group('客流数量', '反映人口活跃度', gooey_options={"columns": 1})
    group1.add_argument('-num_pop', metavar='客流数量所在路径', help="例如: 信科-深圳市整体客流_20210601.txt", widget="FileChooser", nargs='?')
    group1.add_argument('-num_pop_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group1.add_argument('-out_num_pop', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group1.add_argument('--opt1', metavar='可选分析', action='store_true', help='合并小时数据得到全天数量')  
    
    #客流画像
    group2 = parser.add_argument_group('客流画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group2.add_argument('-por_pop', metavar='客流画像所在路径', help="例如: 信科-深圳市整体客流画像_20210601.txt", widget="FileChooser", nargs='?')
    group2.add_argument('-por_pop_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group2.add_argument('-out_por_pop', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group2.add_argument('--opt2', metavar='可选分析', action='store_true', help='合并客流数量估算人群数量')
    group2.add_argument('-num', metavar='客流数量所在路径(可选)', help="例如: 信科-深圳市整体客流_20210601.txt", widget="FileChooser", nargs='?')
    
    #常住数量
    group3 = parser.add_argument_group('常住数量', gooey_options={"columns": 1})
    group3.add_argument('-num_stay', metavar='常住数量所在路径', help="例如: 信科-深圳市整体常住分析-7-9月_longstay_restore_numhome.txt", widget="FileChooser", nargs='?')
    group3.add_argument('-num_stay_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group3.add_argument('-out_num_stay', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group3.add_argument('--opt3', metavar='可选分析', action='store_true', help='计算居住且工作人口数量，需在下方再选择一个常住数量文件')
    group3.add_argument('-num_without', metavar='常住数量2所在路径(可选)', help="如果常住数量上传的是工作人口，请在此上传工作不居住人口数量；如果常住数量上传的是居住人口，请在此上传居住不工作人口数量", widget="FileChooser", nargs='?')
    group3.add_argument('--opt4', metavar='可选分析', action='store_true', help='计算职住比，需在下方再选择一个常住数量文件')
    group3.add_argument('-lw_ratio', metavar='常住数量3所在路径(可选)', help="如果常住数量上传的是工作人口，请在此上传居住人口数量；如果常住数量上传的是居住人口，请在此上传工作人口数量", widget="FileChooser", nargs='?')
    
    #常住画像
    group4 = parser.add_argument_group('常住画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group4.add_argument('-por_stay', metavar='常住画像所在路径', help="例如: 信科-深圳市整体常住画像-7-9月_after1904_home.txt", widget="FileChooser", nargs='?')
    group4.add_argument('-por_stay_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group4.add_argument('-out_por_stay', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group4.add_argument('--opt5', metavar='可选分析', action='store_true', help='合并常住数量估算人群数量')
    group4.add_argument('-stay_merge', metavar='常住数量所在路径(可选)', help="例如: 信科-深圳市整体常住分析-7-9月_longstay_restore_numhome.txt", widget="FileChooser", nargs='?')
    
    #OD分析
    group5 = parser.add_argument_group('OD分析', '反映区域间联系强度', gooey_options={"columns": 1})
    group5.add_argument('-num_OD', metavar='OD数据所在路径', help="例如: 深圳市整体OD分析_20210831.txt", widget="FileChooser", nargs='?')
    group5.add_argument('-O_geo', metavar='O点范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group5.add_argument('-D_geo', metavar='D点范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group5.add_argument('-out_OD', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group5.add_argument('--opt6', metavar='可选分析', action='store_true', help='合并小时数据得到全天数量')
    
    #通勤数量
    group6 = parser.add_argument_group('通勤数量', '反映工作人口或居住人口来源地及通勤数量', gooey_options={"columns": 1})
    group6.add_argument('-num_lw', metavar='通勤数量所在路径', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')
    group6.add_argument('-num_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group6.add_argument('-num_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group6.add_argument('-out_num_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    
    #通勤时间
    group7 = parser.add_argument_group('通勤时间', '反映工作人口或居住人口来源地及通勤时间', gooey_options={"columns": 1})
    group7.add_argument('-time_lw', metavar='通勤时间所在路径', help="例如: 深圳市整体通勤时间_202107.txt", widget="FileChooser", nargs='?')
    group7.add_argument('-time_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group7.add_argument('-time_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group7.add_argument('-out_time_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    
    #通勤方式
    group8 = parser.add_argument_group('通勤方式', '反映工作人口或居住人口来源地及通勤方式', gooey_options={"columns": 1})
    group8.add_argument('-way_lw', metavar='通勤方式所在路径', help="例如: 深圳市整体通勤方式_202107.txt", widget="FileChooser", nargs='?')
    group8.add_argument('-way_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group8.add_argument('-way_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group8.add_argument('-out_way_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group8.add_argument('--opt7', metavar='可选分析', action='store_true', help='合并通勤数量估算各通勤方式使用人数')
    group8.add_argument('-lw_merge', metavar='通勤数量所在路径(可选)', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')
    
    #职住画像
    group9 = parser.add_argument_group('职住画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group9.add_argument('-por_lw', metavar='职住画像所在路径', help="例如: 信科-深圳市整体职住画像_202110.txt", widget="FileChooser", nargs='?')
    group9.add_argument('-por_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group9.add_argument('-por_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group9.add_argument('-out_por_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group9.add_argument('--opt8', metavar='可选分析', action='store_true', help='合并通勤数量估算人群数量')
    group9.add_argument('-lw_por_merge', metavar='通勤数量所在路径(可选)', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')

    args = parser.parse_args()
    
    # *** 运行函数 *** #
    #shp转excel
    if args.geo and args.out:
        dfy = gpd.read_file(args.geo)
        dfy = dfy.to_crs(epsg=4326) #按经纬度读取
        dfy = dfy.explode().reset_index()
        #生成ID
        for index, row in dfy.iterrows():
            dfy.loc[index, 'Id'] = index
        #导出一份对照表
        dfy.to_excel(args.out+'\ID对照表.xlsx',index=False)
        print('已导出ID对照表至',args.out)
        #Polygon转Point
        col = dfy.columns.tolist()
        print(col)
        # new GeoDataFrame with same columns
        nodes = gpd.GeoDataFrame(columns=col)
        for index, row in dfy.iterrows():
            for j in list(row['geometry'].exterior.coords): 
                nodes = nodes.append({'Id':row['Id'], 'geometry':Point(j) },ignore_index=True)
        #生成经纬度
        nodes['x'] = nodes['geometry'].x
        nodes['y'] = nodes['geometry'].y
        #创建工作簿
        wb = xlsxwriter.Workbook(args.out+'\demo.xlsx')
        worksheet = wb.add_worksheet("My sheet")
        x = 0
        y = 0
        worksheet.write(x, y, 'bounds_name')
        worksheet.write(x, y+1, 'bounds')
        #生成目标文件
        prev = -1
        temp = ''
        for index, row in nodes.iterrows():
            if row['Id'] == prev:
                temp += ','+str(row['x'])+','+str(row['y'])
            else:
                #写入上一个bound坐标
                if prev != -1:
                    worksheet.write(x, y+1, temp)
                x += 1
                worksheet.write(x, y, row['Id'])
                temp = str(row['x'])+','+str(row['y'])
            prev = row['Id']
            #处理最后一行        
            if index == nodes.index[-1]:
                worksheet.write(x, y+1, temp)
        wb.close()
        print('已导出excel结果文件至',args.out)
                
    #客流数量
    if args.num_pop and args.num_pop_geo:
        print('分析类型:客流数量')
        df, dfy = read_file(args.num_pop, args.num_pop_geo)
        print('文件读取完成!')
        df = to_wgs(df)
        print('坐标转换完成!')
        if df.columns.__contains__('小时') and args.opt1:
            df = agg_time(df)
            print('全天数量计算完成!')
        dfb = intersect(df, dfy)
        print('空间相交完成!')
        dfb.to_csv(args.out_num_pop+'\客流数量.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_num_pop)
        plot_path = args.out_num_pop+'\\客流数量样方密度.jpg'
        export_plot(dfy, dfb, plot_path, '人数', args)
        print('图像已成功保存至', args.out_num_pop)
        print('==============================================================')
        
    #客流画像
    if args.por_pop and args.por_pop_geo:
        print('分析类型:客流画像')
        df, dfy = read_file(args.por_pop, args.por_pop_geo)
        print('文件读取完成!')
        df = to_wgs(df)
        print('坐标转换完成!')
        if args.num and args.opt2:
            df = merge_num(args.num, df)
            print('客流数量合并完成!')
        dfb = intersect(df, dfy)
        print('空间相交完成!')
        dfb.to_csv(args.out_por_pop+'\客流画像.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_por_pop)
        plot_path = args.out_por_pop+'\\客流画像饼状图.jpg'
        export_pie(dfb, plot_path)
        print('图像已成功保存至', args.out_por_pop)   
        print('==============================================================')

    #常住数量
    if args.num_stay and args.num_stay_geo:
        print('分析类型:常住数量')
        df, dfy = read_file(args.num_stay, args.num_stay_geo)
        print('文件读取完成!')
        df = to_wgs(df)
        print('坐标转换完成!')
        df = merge_longstay(df, args)
        dfb = intersect(df, dfy)
        print('空间相交完成!')
        if args.lw_ratio and args.opt4:
            calc_ratio(dfb)
        dfb.to_csv(args.out_num_stay+'\常住数量.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_num_stay)
        print('==============================================================')
        
    #常住画像
    if args.por_stay and args.por_stay_geo:
        print('分析类型:常住画像')
        df, dfy = read_file(args.por_stay, args.por_stay_geo)
        print('文件读取完成!')
        df = to_wgs(df)
        print('坐标转换完成!')
        if args.stay_merge and args.opt5:
            df = merge_res(args.stay_merge, df)
            print('常住数量合并完成!')
        dfb = intersect(df, dfy)
        print('空间相交完成!')
        dfb.to_csv(args.out_por_stay+'\常住画像.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_por_stay)
        print('==============================================================')

    #OD分析
    if args.num_OD:
        print('分析类型:OD数量')
        df, dfy, dfy2 = read_OD(args.num_OD, args.O_geo, args.D_geo)
        print('文件读取完成!')
        df = OD_to_wgs(df)
        print('坐标转换完成!')
        if df.columns.__contains__('小时') and args.opt6:
            df = OD_agg_time(df, args)
            print('全天数量计算完成!')
        #起点范围
        if args.O_geo and not args.D_geo:
            dfb = O_intersect(df, dfy)
        #终点范围
        elif args.D_geo and not args.O_geo:
            dfb = D_intersect(df, dfy2)
        #两个范围
        elif args.O_geo and args.D_geo:
            temp = O_intersect(df, dfy)
            dfb = D_intersect(temp, dfy2)
        print('空间相交完成!')
        dfb.to_csv(args.out_OD+'\OD分析.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_OD)
        print('==============================================================')
        
    #通勤数量
    if args.num_lw:
        print('分析类型:通勤数量')
        df, dfy, dfy2 = read_OD(args.num_lw, args.num_live_geo, args.num_work_geo)
        print('文件读取完成!')
        df = livework_to_wgs(df)
        print('坐标转换完成!')
        #起点范围
        if args.num_live_geo and not args.num_work_geo:
            dfb = O_intersect(df, dfy)
        #终点范围
        elif args.num_work_geo and not args.num_live_geo:
            dfb = D_intersect(df, dfy2)
        #两个范围
        elif args.num_live_geo and args.num_work_geo:
            temp = O_intersect(df, dfy)
            dfb = D_intersect(temp, dfy2)    
        print('空间相交完成!')
        dfb.to_csv(args.out_num_lw+'\通勤数量.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_num_lw)
        print('==============================================================')
        
    #通勤时间
    if args.time_lw:
        print('分析类型:通勤时间')
        df, dfy, dfy2 = read_OD(args.time_lw, args.time_live_geo, args.time_work_geo)
        print('文件读取完成!')
        df = livework_to_wgs(df)
        print('坐标转换完成!')
        df['平均通勤时间(min)'] = df['平均通勤时间(s)']/60
        #起点范围
        if args.time_live_geo and not args.time_work_geo:
            dfb = O_intersect(df, dfy)
        #终点范围
        elif args.time_work_geo and not args.time_live_geo:
            dfb = D_intersect(df, dfy2)
        #两个范围
        elif args.time_live_geo and args.time_work_geo:
            temp = O_intersect(df, dfy)
            dfb = D_intersect(temp, dfy2)    
        print('空间相交完成!')
        dfb.to_csv(args.out_time_lw+'\通勤时间.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_time_lw)
        print('==============================================================')
        
    #通勤方式
    if args.way_lw:
        print('分析类型:通勤方式')
        df, dfy, dfy2 = read_OD(args.way_lw, args.way_live_geo, args.way_work_geo)
        print('文件读取完成!')
        df = livework_to_wgs(df)
        print('坐标转换完成!')
        if args.lw_merge and args.opt7:
            df = merge_lw(args.lw_merge, df)
            print('通勤数量合并完成!')
        #起点范围
        if args.way_live_geo and not args.way_work_geo:
            dfb = O_intersect(df, dfy)
        #终点范围
        elif args.way_work_geo and not args.way_live_geo:
            dfb = D_intersect(df, dfy2)
        #两个范围
        elif args.way_live_geo and args.way_work_geo:
            temp = O_intersect(df, dfy)
            dfb = D_intersect(temp, dfy2)    
        print('空间相交完成!')
        dfb.to_csv(args.out_way_lw+'\通勤方式.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_way_lw)
        print('==============================================================')
        
    #职住画像
    if args.por_lw:
        print('分析类型:职住画像')
        df, dfy, dfy2 = read_OD(args.por_lw, args.por_live_geo, args.por_work_geo)
        print('文件读取完成!')
        df = livework_to_wgs(df)
        print('坐标转换完成!')
        if args.lw_por_merge and args.opt8:
            df = por_merge(args.lw_por_merge, df)
            print('通勤数量合并完成!')
        #起点范围
        if args.por_live_geo and not args.por_work_geo:
            dfb = O_intersect(df, dfy)
        #终点范围
        elif args.por_work_geo and not args.por_live_geo:
            dfb = D_intersect(df, dfy2)
        #两个范围
        elif args.por_live_geo and args.por_work_geo:
            temp = O_intersect(df, dfy)
            dfb = D_intersect(temp, dfy2)    
        print('空间相交完成!')
        dfb.to_csv(args.out_por_lw+'\职住画像.csv', encoding='UTF-8')
        print('文件已成功保存至', args.out_por_lw)
        print('==============================================================')

# *** 通用函数 *** #
def read_file(data, geofile):
    print('正在读取文件...')
    if data.__contains__('.txt'):
        df = pd.read_csv(data, sep="\t")
    elif data.__contains__('.csv'):
        df = pd.read_csv(data)
    else:
        print('非法数据文件类型！')
    if geofile.__contains__('.shp'):
        dfy = gpd.read_file(geofile)
    else:
        print('非法范围文件类型！')        
    return df, dfy

def to_wgs(df):
    print('正在转换坐标...')
    if df.columns.__contains__('网格中心x坐标'):
        lon = np.empty([len(df["网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["网格中心x坐标"][i], df["网格中心y坐标"][i])
    elif df.columns.__contains__('网格x坐标'):
        lon = np.empty([len(df["网格x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["网格y坐标"]), 1], dtype=float)   
        for i in range(len(df["网格x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["网格x坐标"][i], df["网格y坐标"][i])
    df["x"] = lon
    df["y"] = lat
    del lon
    del lat
    return df

def agg_time(df):
    print('正在计算全天客流数量...')
    df = df.groupby(['网格ID','网格中心x坐标','网格中心y坐标','x','y']).aggregate({'人数': 'sum'}).reset_index()
    return df

def intersect(df, dfy):
    print('正在执行空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['x'], df['y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526) #转投影坐标
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    return dfb    
    
#客流画像专用    
def merge_num(num, df):
    print('正在合并客流数量...')
    dfnum = pd.read_csv(num, sep="\t")
    df.drop(columns=['网格中心x坐标','网格中心y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    dfnum.drop(columns=['网格中心x坐标','网格中心y坐标'],inplace=True)

    if df.columns.__contains__('小时'):
        df_final = pd.merge(df, dfnum, on = ['日期','小时','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 3:51].mul(df_final.人数, 0))
    else:
        df_final = pd.merge(df, dfnum, on = ['日期','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 2:50].mul(df_final.人数, 0))
    return df_final

#常住数量专用
def merge_longstay(df, args):
    if args.num_without and args.opt3:
        print('正在计算居住且工作人口数量...')
        df2 = pd.read_csv(args.num_without, sep="\t")
        if df['人口类型'].iloc[0] == 'home':
            if df2['人口类型'].iloc[0] == 'liveWithoutWork':
                df2.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','居住不工作人数']
                df2.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df_final = pd.merge(df, df2, on = ['日期','区域名称','网格ID'], how = "outer")
                df_final['居住且工作人数'] = df_final['人数']-df_final['居住不工作人数']
                df_final['居住人数'] = df_final['人数']
        elif df['人口类型'].iloc[0] == 'work':
            if df2['人口类型'].iloc[0] == 'workWithoutLive':
                df2.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','工作不居住人数']
                df2.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df_final = pd.merge(df, df2, on = ['日期','区域名称','网格ID'], how = "outer")
                df_final['居住且工作人数'] = df_final['人数']-df_final['工作不居住人数']
                df_final['工作人数'] = df_final['人数']
        df_final.drop(columns=['网格x坐标','网格y坐标','人口类型','人数'],inplace=True)
        print('居住且工作人口计算完成!')
    else:
        df_final = df
    if args.lw_ratio and args.opt4:
        df3 = pd.read_csv(args.lw_ratio, sep="\t")
        temp_name = df3['人口类型'].iloc[0]
        df3.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
        df3.columns = ['日期','区域名称','网格ID',temp_name]
        df_final = pd.merge(df_final, df3, on = ['日期','区域名称','网格ID'], how = "outer")
    else:
        df_final = df
    return df_final

def calc_ratio(df):
    print('正在计算职住比...')
    if df.columns.__contains__('居住人数'):
        ratio = df['work'].sum()/df['居住人数'].sum()
    elif df.columns.__contains__('工作人数'):
        ratio = df['工作人数'].sum()/df['home'].sum()
    elif df['人口类型'].iloc[0] == 'home':
        ratio = df['work'].sum()/df['人数'].sum()
    elif df['人口类型'].iloc[0] == 'work':
        ratio = df['人数'].sum()/df['home'].sum()
    print('分析范围内职住比为:', ratio)

#常住画像专用
def merge_res(num, df):
    print('正在合并常住数量...')
    dfnum = pd.read_csv(num, sep="\t")
    df.drop(columns=['网格x坐标','网格y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    dfnum.drop(columns=['网格x坐标','网格y坐标'],inplace=True)
    df_final = pd.merge(df, dfnum, on = ['日期','网格ID','区域名称','人口类型'], how = 'outer')
    df_final.update(df_final.iloc[:, 4:52].mul(df_final.人数, 0))
    return df_final

#OD专用
def read_OD(data, geofile, geofile2):
    print('正在读取文件...')
    df = ''
    dfy = ''
    dfy2 = ''
    if data.__contains__('.txt'):
        df = pd.read_csv(data, sep="\t")
    else:
        print('非法数据文件类型！')
    if geofile:
        if geofile.__contains__('.shp'):
            dfy = gpd.read_file(geofile)
    if geofile2:
        if geofile2.__contains__('.shp'):
            dfy2 = gpd.read_file(geofile2)
    return df, dfy, dfy2

def OD_to_wgs(df):
    print('正在转换坐标...')
    if df.columns.__contains__('起点网格中心x坐标'):
        lon = np.empty([len(df["起点网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["起点网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["起点网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["起点网格中心x坐标"][i], df["起点网格中心y坐标"][i])
        df["O_x"] = lon
        df["O_y"] = lat
        del lon
        del lat
        
    if df.columns.__contains__('终点网格中心x坐标'):
        lon = np.empty([len(df["终点网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["终点网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["终点网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["终点网格中心x坐标"][i], df["终点网格中心y坐标"][i])
        df["D_x"] = lon
        df["D_y"] = lat
        del lon
        del lat
    return df

def OD_agg_time(df, args):
    print('正在计算全天OD数量...')
    #起点范围
    if args.O_geo and not args.D_geo:
        df = df.groupby(['起点区域名称','终点区域名称','网格ID','起点网格中心x坐标','起点网格中心y坐标','O_x','O_y']).aggregate({'数量': 'sum'}).reset_index()
    #终点范围
    elif args.D_geo and not args.O_geo:
        df = df.groupby(['起点区域名称','终点区域名称','网格ID','终点网格中心x坐标','终点网格中心y坐标','D_x','D_y']).aggregate({'数量': 'sum'}).reset_index()
    #两个范围
    elif args.O_geo and args.D_geo:
        df = df.groupby(['起点区域名称','终点区域名称','起点网格ID','终点网格ID','起点网格中心x坐标','起点网格中心y坐标','终点网格中心x坐标','终点网格中心y坐标','O_x','O_y','D_x','D_y']).aggregate({'数量': 'sum'}).reset_index()
    return df

def O_intersect(df, dfy):
    print('正在执行起点范围空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['O_x'], df['O_y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    if dfb.columns.__contains__('index_right'):
        dfb.drop(['index_right'], axis=1, inplace=True)
    return dfb

def D_intersect(df, dfy):
    print('正在执行终点范围空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['D_x'], df['D_y']))
    dfx.crs = 'EPSG:4326' #按WGS84读取
    dfx = dfx.to_crs(epsg=4526) #转投影坐标
    dfy = dfy.to_crs(epsg=4526)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    return dfb

#职住专用
def livework_to_wgs(df):
    print('正在转换坐标...')
    if df.columns.__contains__('居住地网格中心x坐标'):
        lon = np.empty([len(df["居住地网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["居住地网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["居住地网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["居住地网格中心x坐标"][i], df["居住地网格中心y坐标"][i])
        df["O_x"] = lon
        df["O_y"] = lat
        del lon
        del lat
        
    if df.columns.__contains__('工作地网格中心x坐标'):
        lon = np.empty([len(df["工作地网格中心x坐标"]), 1], dtype=float)
        lat = np.empty([len(df["工作地网格中心y坐标"]), 1], dtype=float)   
        for i in range(len(df["工作地网格中心x坐标"])):
            lon[i], lat[i] = gcj2wgs(df["工作地网格中心x坐标"][i], df["工作地网格中心y坐标"][i])
        df["D_x"] = lon
        df["D_y"] = lat
        del lon
        del lat
    return df

def merge_lw(num, df):
    print('正在合并通勤数量...')
    dfnum = pd.read_csv(num, sep="\t")
    df_final = pd.merge(dfnum, df, on = ['日期','居住地名称','起点网格ID','居住地网格中心x坐标','居住地网格中心y坐标','工作地名称','终点网格ID','工作地网格中心x坐标','工作地网格中心y坐标'], how = 'outer')
    df_final.update(df_final.iloc[:, 9:13].mul(df_final.人数, 0))
    return df_final

def por_merge(num, df):
    print('正在合并通勤数量...')
    dfnum = pd.read_csv(num, sep="\t")
    df.drop(columns=['居住地网格中心x坐标','居住地网格中心y坐标','工作地网格中心x坐标','工作地网格中心y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    dfnum.drop(columns=['居住地网格中心x坐标','居住地网格中心y坐标','工作地网格中心x坐标','工作地网格中心y坐标'],inplace=True)
    df_final = pd.merge(dfnum, df, on = ['日期','居住地名称','起点网格ID','工作地名称','终点网格ID'], how = 'outer')
    df_final.update(df_final.iloc[:, 5:53].mul(df_final.人数, 0))
    return df_final

def export_plot(dfy, dfb, plot_path, variable, args):
    print('正在绘图中...')
    #参数转换数值
    args.cellsize = int(args.cellsize)
    args.vmin = int(args.vmin)
    args.k = int(args.k)
    args.alpha = float(args.alpha)
    #加载底图
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.epsg('4526'))
    ax.set_extent([dfy['geometry'].total_bounds[0]-100, dfy['geometry'].total_bounds[2]+100, dfy['geometry'].total_bounds[1]-100, dfy['geometry'].total_bounds[3]+100],crs=ccrs.epsg('4526'))
    if args.basemap == '天地图':
        request = TDT_vec()
    elif args.basemap == 'Mapbox':
        request = MB_vec()
    ax.add_image(request, 15)
    ax.set_title(args.title, fontsize=15)
    #绘制渔网图
    coord1 = (dfy['geometry'].total_bounds[0]-100, dfy['geometry'].total_bounds[3]+100)
    coord3 = (dfy['geometry'].total_bounds[2]+100, dfy['geometry'].total_bounds[1]-100)
    coord2 = (coord3[0],coord1[1])
    coord4 = (coord1[0],coord3[1])
    rectangle = Polygon([coord1,coord2,coord3,coord4])
    rectangle = gpd.GeoDataFrame([rectangle],columns=['geometry'])
    rectangle = rectangle.set_crs(epsg=4526)
    coords = rectangle['geometry'].bounds.values[0]
    loc_all = '{},{},{},{}'.format(coords[0],coords[3],coords[2],coords[1])
    nets = lng_lat(loc_all, args.cellsize)
    netfish = gpd.GeoDataFrame([getPolygon(i[0],i[1]) for i in nets],columns=['geometry'])
    netfish = netfish.set_crs(epsg=4526)
    #渔网与dfb空间相交
    del dfb['index_right']
    dfo = gpd.sjoin(netfish, dfb, op='contains')
    dfy.boundary.plot(ax=ax, linestyle='--', edgecolor='grey', zorder=2) #绘制范围
    dfo = dfo[dfo[variable]>=args.vmin]
    dfo.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, k=args.k, alpha=args.alpha, zorder=1) #绘制样方密度图
    #自定义图例
    handles, labels = ax.get_legend_handles_labels()
    cmap = plt.get_cmap(args.cmap)
    if args.scheme == 'natural_breaks':
        nb = mc.NaturalBreaks(dfo[variable], k=args.k)
    elif args.scheme == 'equal_interval':
        nb = mc.EqualInterval(dfo[variable], k=args.k)
    elif args.scheme == 'fisher_jenks':
        nb = mc.FisherJenks(dfo[variable], k=args.k)
    elif args.scheme == 'headtail_breaks':
        nb = mc.HeadTailBreaks(dfo[variable], k=args.k)
    elif args.scheme == 'jenks_caspall':
        nb = mc.JenksCaspall(dfo[variable], k=args.k)
    elif args.scheme == 'quantiles':
        nb = mc.Quantiles(dfo[variable], k=args.k)
    elif args.scheme == 'user_defined':
        print('此功能暂未开放')      
    bins = nb.bins
    LegendElement = [mpatches.Patch(facecolor=cmap(0), label=f'{args.vmin} - {int(bins[0])}')] + [mpatches.Patch(facecolor=cmap(_*0.25), label=f'{int(bins[_-1])} - {int(bins[_])}') for _ in range(1,args.k)]
    ax.legend(handles = LegendElement, loc='lower right', fontsize=10, title='图例', shadow=True)
    ax.axis('off')
    fig.savefig(plot_path, dpi=400)

def export_pie(dfb, plot_path):
    print('qnmd')
    #性别、年龄、教育水平、收入水平（工作、行业）
    #FIXME
    

#切割渔网
def lng_lat(loc_all, div):
    #提取经纬度
    lngH = float(loc_all.split(',')[2])
    lngL = float(loc_all.split(',')[0])
    latH = float(loc_all.split(',')[1])
    latL = float(loc_all.split(',')[3])
    #按照一个数值切割纬度
    lat_ls = [str(latH)]
    while latH - latL > 0:
        latH = latH - div
        lat_ls.append('{:.2f}'.format(latH))
    #按照一个数值切割经度
    lng_ls = [str(lngH)]
    while lngH - lngL > 0:
        lngH = lngH - div
        lng_ls.append('{:.2f}'.format(lngH))
    #获取经纬度列表
    lat = lat_ls
    lng = sorted(lng_ls)
    #组合经纬度成为坐标
    lst = []
    for a in lat:
        for n in lng:
            lst.append('{},{}'.format(n, a))
    #创建一个嵌套列表，便于后面进行坐标串组合
    lst1 = []
    for i in range(len(lat)):
        lst1.append(lst[i * len(lng):(i + 1) * len(lng)])
    #坐标串组合
    lsta = []
    for a in range(0, len(lat) - 1):
        for n in range(0, len(lng) - 1):
            coords = (float(lst1[a][n].split(',')[0]),float(lst1[a][n].split(',')[1])),\
                     (float(lst1[a+1][n+1].split(',')[0]),float(lst1[a+1][n+1].split(',')[1]))
            lsta.append(coords)
    return lsta

def getPolygon(coord1,coord3):
    coord1 = coord1
    coord3 = coord3
    coord2 = (coord3[0],coord1[1])
    coord4 = (coord1[0],coord3[1])
    rectangle = Polygon([coord1,coord2,coord3,coord4])
    return rectangle

if __name__ == "__main__":
    main()
