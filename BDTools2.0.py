# -*- coding: utf-8 -*-
"""
BDTools V2.0
@Liyao Zhang
Start Date 1/10/2022
Last Edit 7/29/2022

地理坐标系 EPSG 4326/4490 投影坐标系 EPSG 4547/4526
常住人口自定义断点 100米网格 80,200,400,800；500米网格 2000,5000,10000,20000
"""
import pandas as pd
import geopandas as gpd
import numpy as np
import xlsxwriter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import mapclassify as mc
from functools import reduce
from gooey import Gooey, GooeyParser
from GCS_Conversion import gcj2wgs
from shapely.geometry import Point, Polygon, LineString
from geovoronoi import voronoi_regions_from_coords, points_to_coords
import cartopy.io.img_tiles as cimgt
import cartopy.crs as ccrs
from palettable.cmocean.sequential import Dense_20
from PIL import Image

plt.rcParams["font.family"] = "SimHei"
plt.rcParams.update({'figure.max_open_warning': 0})
# MapBox底图
class MB_vec_default(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        access_token = 'pk.eyJ1IjoibW9leDEwMDIzNiIsImEiOiJjbDF1ZW1oYmYybXAyM2NvMmczNmRlOXptIn0.HAW1OjKgMO_cBdSWVvMKjg'
        url = (f'https://api.mapbox.com/styles/v1/moex100236/cl1ucnkj3001y14o6m8ynk3w2/tiles/256'
               f'/{z}/{x}/{y}?access_token={access_token}'.format(z=z, y=y, x=x, token=access_token))
        return url
class MB_vec_backup(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        access_token = 'pk.eyJ1IjoianVueWFvLXhpYW8iLCJhIjoiY2o3Y29zMGRoMDBqMTM0bXR5d2VlenpycSJ9.i0SXqgJ7Bhf8UhJ04Ygq_A'
        url = (f'https://api.mapbox.com/styles/v1/junyao-xiao/ckvjgucwz13sj14pf5mf6wlq9/tiles/256'
               f'/{z}/{x}/{y}?access_token={access_token}'.format(z=z, y=y, x=x, token=access_token))
        return url
# 天地图矢量底图
class TDT_vec(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        key = 'abc457154134c560ff8e160e0c509be5'
        url = 'http://t0.tianditu.gov.cn/DataServer?T=vec_w&x=%s&y=%s&l=%s&tk=%s' % (x, y, z, key)
        return url
# 天地图影像底图
class TDT_img(cimgt.GoogleWTS):
    def _image_url(self, tile):
        x, y, z = tile
        key = 'abc457154134c560ff8e160e0c509be5'
        url = 'http://t0.tianditu.gov.cn/DataServer?T=img_w&x=%s&y=%s&l=%s&tk=%s' % (x, y, z, key)
        return url

@Gooey(program_name="BDTools",
       default_size=(680, 800),
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
                'url': 'https://shimo.im/docs/WlArzE668EtDZzA2'
            }]
    }]
)
def main():
    parser = GooeyParser()
    # *** 界面搭建及参数获取 *** #
    #参数设置
    group_vis = parser.add_argument_group('设置', '选择默认参数或自定义参数', gooey_options={"columns": 2})
    group_vis.add_argument('-wgs', metavar='转换坐标系', action='store_true', help='GCJ02 to WGS84')
    group_vis.add_argument('-replot', metavar='重新出图', action='store_true', help='上传数据和范围重新可视化')
    group_vis.add_argument('-title', metavar='图片标题', widget="TextField", default='*标题将自动匹配数据类型，请忽略*')
    group_vis.add_argument('-basemap', metavar='底图样式', choices=['Mapbox(首选key)','Mapbox(备选key)','天地图矢量','天地图影像'], default='Mapbox(首选key)')
    group_vis.add_argument('-cellsize', metavar='网格大小(客流/常住分析)', help='单位:米', choices=['100','200','500','1000','自定义范围'], default='100')
    group_vis.add_argument('-ODcellsize', metavar='网格大小(OD/通勤分析)', help='单位:米', choices=['100','200','500','1000','自定义范围'], default='500')
    group_vis.add_argument('-cmap', metavar='色调', choices=['autumn_r','Dense_20','Greys','Reds','Oranges','OrRd','YlOrRd','YlOrBr','YlGnBu','hot','Spectral'], default='OrRd')
    group_vis.add_argument('-scheme', metavar='分级方式', choices=['equal_interval','fisher_jenks','jenks_caspall','natural_breaks','quantiles','user_defined'], default='natural_breaks')
    group_vis.add_argument('-k', metavar='数据分级数', help="'user_defined'请选择自定义间断点数+1 例如：5,10,50,100分级数为5", widget="Slider", default=5)
    group_vis.add_argument('-userbin', metavar='自定义间断点', help="请在分级方式选择'user_defined'后输入并用逗号隔开 例如: 5,10,50,100", widget="TextField")
    group_vis.add_argument('-vmin', metavar='最小值', help='可视化显示的最小值', widget="Slider", default=1)
    group_vis.add_argument('-alpha', metavar='透明度', help='0-1之间', widget="DecimalField", default=1)
    group_vis.add_argument('-linewidth', metavar='OD图线宽系数', help='建议选择1以上', widget="DecimalField", default=1.5)
    group_vis.add_argument('-custom', metavar='自定义聚合范围', help='网格大小选择自定义范围后上传文件', widget="FileChooser", default=r'D:\范围\深圳市地籍网站行政区划2021\深圳街道.shp')
    
    #shp转excel
    group0 = parser.add_argument_group('shp转excel', '可用于申请范围内整体画像、通勤方式等含比例数据', gooey_options={"columns": 1})
    group0.add_argument('-geo', metavar='shp文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="MultiFileChooser", nargs='*')
    group0.add_argument('-out', metavar='结果文件夹保存路径', widget="DirChooser", nargs='?')
    
    #客流数量
    group1 = parser.add_argument_group('客流数量', '反映人口活跃度', gooey_options={"columns": 1})
    group1.add_argument('-num_pop', metavar='客流数量所在路径', help="例如: 信科-深圳市整体客流_20210601.txt", widget="FileChooser", nargs='?')
    group1.add_argument('-num_pop_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="MultiFileChooser", nargs='*')
    group1.add_argument('-out_num_pop', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group1.add_argument('-opt1', metavar='可选分析', help='针对含小时数据，如果选择生成动图请在下方选择起止时间', choices=['合并小时数据得到全天数量','生成包含每小时数据的动图'])
    group1.add_argument('-npstart', metavar='开始时间（包含）', help='请在0-23中选择一个数字', widget="Slider", default=0)
    group1.add_argument('-npend', metavar='结束时间（不包含）', help='请在1-24中选择一个数字', widget="Slider", default=24)
    
    #客流画像
    group2 = parser.add_argument_group('客流画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group2.add_argument('-por_pop', metavar='客流画像所在路径', help="例如: 信科-深圳市整体客流画像_20210601.txt", widget="FileChooser", nargs='?')
    group2.add_argument('-por_pop_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="MultiFileChooser", nargs='*')
    group2.add_argument('-out_por_pop', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group2.add_argument('--opt2', metavar='可选分析', action='store_true', help='合并客流数量估算人群数量')
    group2.add_argument('-num', metavar='客流数量所在路径(可选)', help="例如: 信科-深圳市整体客流_20210601.txt", widget="FileChooser", nargs='?')
    
    #常住数量
    group3 = parser.add_argument_group('常住数量', gooey_options={"columns": 1})
    group3.add_argument('-num_month', metavar='分析月份', help="输入6位数字 例如: 202103", widget="TextField", nargs='?')
    group3.add_argument('-num_stay', metavar='常住数量所在路径', help="例如: 信科-深圳市整体常住分析-7-9月_longstay_restore_numhome.txt", widget="FileChooser", nargs='?')
    group3.add_argument('-num_stay_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="MultiFileChooser", nargs='*')
    group3.add_argument('-out_num_stay', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group3.add_argument('--opt3', metavar='可选分析', action='store_true', help='计算居住且工作人口数量，需在下方再选择两个常住数量文件')    
    group3.add_argument('-num_without1', metavar='常住数量2所在路径(可选)', help="如果常住数量上传的是工作人口，请在此上传工作不居住人口数量；如果常住数量上传的是居住人口，请在此上传居住不工作人口数量", widget="FileChooser", nargs='?')
    group3.add_argument('-num_without2', metavar='常住数量3所在路径(可选)', widget="FileChooser", nargs='?')    
    group3.add_argument('--opt4', metavar='可选分析', action='store_true', help='计算职住比，需在下方再选择一个常住数量文件')
    group3.add_argument('-lw_ratio', metavar='常住数量4所在路径(可选)', help="如果常住数量上传的是工作人口，请在此上传居住人口数量；如果常住数量上传的是居住人口，请在此上传工作人口数量", widget="FileChooser", nargs='?')
    
    #常住画像
    group4 = parser.add_argument_group('常住画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group4.add_argument('-por_month', metavar='分析月份', help="输入6位数字 例如: 202103", widget="TextField", nargs='?')
    group4.add_argument('-por_stay', metavar='常住画像所在路径', help="例如: 信科-深圳市整体常住画像-7-9月_after1904_home.txt", widget="FileChooser", nargs='?')
    group4.add_argument('-por_stay_geo', metavar='范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="MultiFileChooser", nargs='*')
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
    group5.add_argument('-rev0', metavar='运行模式', choices=['以分析范围为起点','以分析范围为终点','both'], help='如果选择both，请在O点上传分析范围，D点上传辐射范围(如全市范围)，生成从分析范围前往全市客流分布及分析范围内客流来源分布')
    group5.add_argument('-pt0', metavar='可视化选项', choices=['样方密度图', 'OD图'], help='生成图像类型', default='样方密度图')
    
    #通勤数量
    group6 = parser.add_argument_group('通勤数量', '反映工作人口或居住人口来源地及通勤数量', gooey_options={"columns": 1})
    group6.add_argument('-num_lw', metavar='通勤数量所在路径', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')
    group6.add_argument('-num_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group6.add_argument('-num_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group6.add_argument('-out_num_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group6.add_argument('-rev1', metavar='运行模式', choices=['以分析范围为居住地','以分析范围为工作地','both'], help='如果选择both，请在居住地上传分析范围，工作地上传辐射范围(如全市范围)，生成分析范围内居住人口在全市工作地分布及范围内就业人口在全市居住地分布')
    group6.add_argument('-pt1', metavar='可视化选项', choices=['样方密度图', 'OD图'], help='生成图像类型', default='样方密度图')
    
    #通勤时间
    group7 = parser.add_argument_group('通勤时间', '反映工作人口或居住人口来源地及通勤时间', gooey_options={"columns": 1})
    group7.add_argument('-time_lw', metavar='通勤时间所在路径', help="例如: 深圳市整体通勤时间_202107.txt", widget="FileChooser", nargs='?')
    group7.add_argument('-time_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group7.add_argument('-time_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group7.add_argument('-out_time_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group7.add_argument('--opt10', metavar='可选分析', action='store_true', help='合并通勤数量，用于筛选超过一定OD数量的通勤时间')
    group7.add_argument('-time_merge', metavar='通勤数量所在路径(可选)', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')    
    group7.add_argument('-rev2', metavar='运行模式', choices=['以分析范围为居住地','以分析范围为工作地','both'], help='如果选择both，请在居住地上传分析范围，工作地上传辐射范围(如全市范围)，生成分析范围内居住人口前往全市通勤时间分布及范围内就业人口从全市出发通勤时间分布')
    group7.add_argument('-pt2', metavar='可视化选项', choices=['样方密度图', 'OD图'], help='生成图像类型', default='样方密度图')
    
    #通勤方式
    group8 = parser.add_argument_group('通勤方式', '反映工作人口或居住人口来源地及通勤方式', gooey_options={"columns": 1})
    group8.add_argument('-way_lw', metavar='通勤方式所在路径', help="例如: 深圳市整体通勤方式_202107.txt", widget="FileChooser", nargs='?')
    group8.add_argument('-way_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group8.add_argument('-way_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group8.add_argument('-out_way_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group8.add_argument('--opt7', metavar='可选分析', action='store_true', help='合并通勤数量估算各通勤方式使用人数')
    group8.add_argument('-lw_merge', metavar='通勤数量所在路径(可选)', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')
    group8.add_argument('-rev3', metavar='运行模式', choices=['以分析范围为居住地','以分析范围为工作地','both'], help='如果选择both，请在居住地上传分析范围，生成分析范围内居住人口前往全市通勤方式及范围内就业人口从全市出发通勤方式')
    
    #职住画像
    group9 = parser.add_argument_group('职住画像', '性别年龄学历收入等多维分析', gooey_options={"columns": 1})
    group9.add_argument('-por_lw', metavar='职住画像所在路径', help="例如: 信科-深圳市整体职住画像_202110.txt", widget="FileChooser", nargs='?')
    group9.add_argument('-por_live_geo', metavar='居住范围文件所在路径', help="例如: 五和地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group9.add_argument('-por_work_geo', metavar='工作范围文件所在路径', help="例如: 桃源村地铁站500m范围.shp", widget="FileChooser", nargs='?')
    group9.add_argument('-out_por_lw', metavar='结果文件保存路径', help="默认保存为csv格式", widget="DirChooser", nargs='?')
    group9.add_argument('--opt8', metavar='可选分析', action='store_true', help='合并通勤数量估算人群数量')
    group9.add_argument('-lw_por_merge', metavar='通勤数量所在路径(可选)', help="例如: 深圳市整体职住分析_202107.txt", widget="FileChooser", nargs='?')
    group9.add_argument('-rev4', metavar='运行模式', choices=['以分析范围为居住地','以分析范围为工作地','both'], help='如果选择both，请在居住地上传分析范围，生成分析范围内居住人口画像及范围内就业人口画像')

    args = parser.parse_args()
    
    # *** 运行函数 *** #
    #shp转excel
    if args.geo and args.out:
        geos = args.geo
        for i in range(len(geos)):
            args.geo = geos[i]
            dfy = gpd.read_file(args.geo)
            dfy.dropna(axis=0, how='any', subset=['geometry'], inplace=True)
            dfy = dfy.to_crs(epsg=4490) #按经纬度读取
            dfy = dfy.explode().reset_index()
            #生成ID
            for index, row in dfy.iterrows():
                dfy.loc[index, 'Id'] = index
            #导出一份对照表
            dfy.to_excel(args.out+'\ID对照表'+str(i+1)+'.xlsx',index=False)
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
            wb = xlsxwriter.Workbook(args.out+'\demo'+str(i+1)+'.xlsx')
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
    if args.num_pop and args.num_pop_geo and not args.replot:
        geos = args.num_pop_geo
        for i in range(len(geos)):
            args.num_pop_geo = geos[i]
            name = parse_path(args.num_pop_geo)
            print('分析类型:客流数量')
            df, dfy = read_file(args.num_pop, args.num_pop_geo)
            print('文件读取完成!')
            if args.wgs:
                df = to_wgs(df)
                print('坐标转换完成!')
            if df.columns.__contains__('小时') and args.opt1 == '合并小时数据得到全天数量':
                df = agg_time(df)
                print('全天数量计算完成!')
            dfb = intersect(df, dfy)
            print('空间相交完成!')
            dfb.to_csv(args.out_num_pop+'\客流数量_'+name+'.csv', encoding='UTF-8', index=False)
            print('文件已成功保存至', args.out_num_pop)
            if args.opt1 == '生成包含每小时数据的动图':
                start = int(args.npstart)
                end = int(args.npend)
                paths = []
                for k in range(start, end):
                    dfg = dfb[dfb['小时'] == k]
                    plot_path = args.out_num_pop+'\\客流数量样方密度'+str(k)+'时.jpg'
                    paths.append(plot_path)
                    args.title = '客流数量'
                    export_plot(dfy, dfg, plot_path, '人数', args)
                outpath = args.out_num_pop+'\\每小时客流数量样方密度_'+name+'.gif'
                pic_to_gif(paths, outpath)
            else:
                plot_path = args.out_num_pop+'\\客流数量样方密度_'+name+'.jpg' 
                args.title = '客流数量'
                export_plot(dfy, dfb, plot_path, '人数', args)
            print('图像已成功保存至', args.out_num_pop)
            print('==============================================================')
    elif args.num_pop and not args.num_pop_geo and args.wgs:
        print('分析类型:客流数量（只转坐标）')
        df = grab_and_go(args.num_pop)
        print('坐标转换完成!')
        df.to_csv(args.out_num_pop+'\客流数量'+str(df['日期'].iloc[0])+'_wgs84.csv', encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_num_pop)
    elif args.num_pop and args.num_pop_geo and args.replot:
        print('分析类型:客流数量（重新出图）')
        df, dfy = reload_point(args.num_pop, args.num_pop_geo[0])
        name = parse_path(args.num_pop_geo[0])
        if args.opt1 == '生成包含每小时数据的动图':
            start = int(args.npstart)
            end = int(args.npend)
            paths = []
            for k in range(start, end):
                dfg = df[df['小时'] == k]
                plot_path = args.out_num_pop+'\\客流数量样方密度'+str(k)+'时.jpg'
                paths.append(plot_path)
                args.title = '客流数量'
                export_plot(dfy, dfg, plot_path, '人数', args)
            outpath = args.out_num_pop+'\\每小时客流数量样方密度(新)_'+name+'.gif'
            pic_to_gif(paths, outpath)
        else:
            plot_path = args.out_num_pop+'\\客流数量样方密度(新)_'+name+'.jpg'
            args.title = '客流数量'
            export_plot(dfy, df, plot_path, '人数', args)
        print('图像已成功保存至', args.out_num_pop)
        print('==============================================================')
        
    #客流画像
    if args.por_pop and args.por_pop_geo and not args.replot:
        print('分析类型:客流画像')
        geos = args.por_pop_geo
        df, dfy_fake = read_file(args.por_pop)
        print('文件读取完成!')
        if args.wgs:
            df = to_wgs(df)
            print('坐标转换完成!')
        if args.num and args.opt2:
            df = merge_num(args.num, df)
            print('客流数量合并完成!')
        
        for i in range(len(geos)):
            args.por_pop_geo = geos[i]
            name = parse_path(args.por_pop_geo)
            dfy = gpd.read_file(args.por_pop_geo)
    
            dfb = intersect(df, dfy)
            print('空间相交完成!')
            dfb.to_csv(args.out_por_pop+'\客流画像_'+name+'.csv', encoding='UTF-8', index=False)
            print('文件已成功保存至', args.out_por_pop)
            plot_path = args.out_por_pop+'\\客流画像饼状图_'+name+'.jpg'
            args.title = '客流画像'
            export_pie(dfb, plot_path, args)
            print('图像已成功保存至', args.out_por_pop)   
            print('==============================================================')
    elif args.por_pop and not args.por_pop_geo and args.wgs:
        print('分析类型:客流画像（只转坐标）')
        df = grab_and_go(args.por_pop)
        print('坐标转换完成!')
        df.to_csv(args.out_por_pop+'\客流画像'+str(df['日期'].iloc[0])+'_wgs84.csv', encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_por_pop)
    elif args.por_pop and args.replot:
        print('分析类型:客流画像（重新出图）')
        df = pd.read_csv(args.por_pop)
        plot_path = args.out_por_pop+'\\客流画像饼状图(新).jpg'
        args.title = '客流画像'
        export_pie(df, plot_path, args)
        print('图像已成功保存至', args.out_por_pop)
        print('==============================================================')

    #常住数量
    if args.num_stay and args.num_stay_geo and not args.replot:
        geos = args.num_stay_geo
        for i in range(len(geos)):
            args.num_stay_geo = geos[i]
            name = parse_path(args.num_stay_geo)
            print('分析类型:常住数量')
            df, dfy = read_file(args.num_stay, args.num_stay_geo)
            print('文件读取完成!')
            if args.wgs:
                df = to_wgs(df)
                print('坐标转换完成!')
            if args.num_month:
                args.num_month = int(args.num_month)
                df = df[df['日期'] == args.num_month]
            df = merge_longstay(df, args)
            dfb = intersect(df, dfy)
            print('空间相交完成!')
            if args.lw_ratio and args.opt4:
                calc_ratio(dfb)
            dfb.to_csv(args.out_num_stay+'\常住数量_'+name+'.csv', encoding='UTF-8', index=False)
            print('文件已成功保存至', args.out_num_stay)

            if dfb.columns.__contains__('home'):
                plot_path = args.out_num_stay+'\\居住人口样方密度_'+name+'.jpg'
                args.title = '居住人口'
                export_plot(dfy, dfb, plot_path, 'home', args)
            elif dfb.columns.__contains__('居住人数'):
                plot_path = args.out_num_stay+'\\居住人口样方密度_'+name+'.jpg'
                args.title = '居住人口'
                export_plot(dfy, dfb, plot_path, '居住人数', args)
            if dfb.columns.__contains__('work'):
                plot_path = args.out_num_stay+'\\就业人口样方密度_'+name+'.jpg'
                args.title = '就业人口'
                export_plot(dfy, dfb, plot_path, 'work', args)
            elif dfb.columns.__contains__('工作人数'):
                plot_path = args.out_num_stay+'\\就业人口样方密度_'+name+'.jpg'
                args.title = '就业人口'
                export_plot(dfy, dfb, plot_path, '工作人数', args)
            else:               
                if dfb['人口类型'].iloc[0] == 'home':
                    plot_path = args.out_num_stay+'\\居住人口样方密度_'+name+'.jpg'
                    args.title = '居住人口'
                elif dfb['人口类型'].iloc[0] == 'work':
                    plot_path = args.out_num_stay+'\\就业人口样方密度_'+name+'.jpg'
                    args.title = '就业人口'              
                export_plot(dfy, dfb, plot_path, '人数', args)
            print('图像已成功保存至', args.out_num_stay)
            print('==============================================================')
    elif args.num_stay and not args.num_stay_geo and args.wgs:
        print('分析类型:常住数量（只转坐标）')
        df = grab_and_go(args.num_stay)
        print('坐标转换完成!')
        df.to_csv(args.out_num_stay+'\常住数量'+df['人口类型'].iloc[0]+'_wgs84.csv', encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_num_stay)
    elif args.num_stay and args.num_stay_geo and args.replot:
        print('分析类型:常住数量（重新出图）')
        dfb, dfy = reload_point(args.num_stay, args.num_stay_geo[0])
        name = parse_path(args.num_stay_geo[0])
        if dfb.columns.__contains__('home'):
            plot_path = args.out_num_stay+'\\居住人口样方密度(新)_'+name+'.jpg'
            args.title = '居住人口'
            export_plot(dfy, dfb, plot_path, 'home', args)
        elif dfb.columns.__contains__('居住人数'):
            plot_path = args.out_num_stay+'\\居住人口样方密度(新)_'+name+'.jpg'
            args.title = '居住人口'
            export_plot(dfy, dfb, plot_path, '居住人数', args)
        if dfb.columns.__contains__('work'):
            plot_path = args.out_num_stay+'\\就业人口样方密度(新)_'+name+'.jpg'
            args.title = '就业人口'
            export_plot(dfy, dfb, plot_path, 'work', args)
        elif dfb.columns.__contains__('工作人数'):
            plot_path = args.out_num_stay+'\\就业人口样方密度(新)_'+name+'.jpg'
            args.title = '就业人口'
            export_plot(dfy, dfb, plot_path, '工作人数', args)
        else:
            if dfb['人口类型'].iloc[0] == 'home':
                plot_path = args.out_num_stay+'\\居住人口样方密度(新)_'+name+'.jpg'
                args.title = '居住人口'
            elif dfb['人口类型'].iloc[0] == 'work':
                plot_path = args.out_num_stay+'\\就业人口样方密度(新)_'+name+'.jpg'
                args.title = '就业人口'              
            export_plot(dfy, dfb, plot_path, '人数', args)
        print('图像已成功保存至', args.out_num_stay)
        print('==============================================================')
        
    #常住画像
    if args.por_stay and args.por_stay_geo and not args.replot:
        geos = args.por_stay_geo
        for i in range(len(geos)):
            args.por_stay_geo = geos[i]
            name = parse_path(args.por_stay_geo)
            print('分析类型:常住画像')
            df, dfy = read_file(args.por_stay, args.por_stay_geo)
            print('文件读取完成!')
            if args.wgs:
                df = to_wgs(df)
                print('坐标转换完成!')
            if args.por_month:
                args.por_month = int(args.por_month)
                df = df[df['日期'] == args.por_month]
            if args.stay_merge and args.opt5:
                df = merge_res(args.stay_merge, df)
                print('常住数量合并完成!')
            dfb = intersect(df, dfy)
            print('空间相交完成!')
            dfb.to_csv(args.out_por_stay+'\常住画像'+dfb['人口类型'].iloc[0]+name+'.csv', encoding='UTF-8', index=False)
            print('文件已成功保存至', args.out_por_stay)
            plot_path = args.out_por_stay+'\\常住画像饼状图'+dfb['人口类型'].iloc[0]+name+'.jpg'
            args.title = '常住画像'
            export_pie(dfb, plot_path, args)
            print('图像已成功保存至', args.out_por_stay)
            print('==============================================================')
    elif args.por_stay and not args.por_stay_geo and args.wgs:
        print('分析类型:常住画像（只转坐标）')
        df = grab_and_go(args.por_stay)
        print('坐标转换完成!')
        df.to_csv(args.out_por_stay+'\常住画像'+df['人口类型'].iloc[0]+'_wgs84.csv', encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_por_stay)
    elif args.por_stay and args.replot:
        print('分析类型:常住画像（重新出图）')
        df = pd.read_csv(args.por_stay)
        plot_path = args.out_por_stay+'\\常住画像饼状图(新)'+df['人口类型'].iloc[0]+'.jpg'
        args.title = '常住画像'
        export_pie(df, plot_path, args)
        print('图像已成功保存至', args.out_por_stay)
        print('==============================================================')

    #OD分析
    if args.num_OD and not args.replot:
        filename = '\OD分析.csv'
        print('分析类型:OD数量')
        args.cellsize = args.ODcellsize
        df, dfy, dfy2 = read_OD(args.num_OD, args.O_geo, args.D_geo)
        O_name = parse_path(args.O_geo)
        D_name = parse_path(args.D_geo)
        print('文件读取完成!')
        if args.wgs:
            df = OD_to_wgs(df)
            print('坐标转换完成!')
        if df.columns.__contains__('小时') and args.opt6:
            df = OD_agg_time(df, args)
            print('全天数量计算完成!')
        if args.O_geo and args.D_geo and args.rev0 == '以分析范围为起点':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt0 == '样方密度图':
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\OD去向分布_'+O_name+'.csv'
            plot_path = args.out_OD+'\\OD去向分布地_'+O_name+'.jpg'
            args.title = 'OD去向分布(O点:'+O_name+' D点:'+D_name+')'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '数量', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '数量', args, dfy)
            dfb = df_O
        elif args.O_geo and args.D_geo and args.rev0 == '以分析范围为终点':
            temp = D_intersect(df, dfy2)
            df_D = temp
            if '深圳' not in O_name:
                df_D = O_intersect(temp, dfy)
            elif args.pt0 == '样方密度图':
                df_D = OD_plot(temp, dfy, 'D') #转换描点范围
            filename = '\OD来源分布_'+D_name+'.csv'
            plot_path = args.out_OD+'\\OD来源分布地_'+D_name+'.jpg'
            args.title = 'OD来源分布(O点:'+O_name+' D点:'+D_name+')'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy, df_D, plot_path, '数量', args, dfy2)
            else:           
                export_plot(dfy, df_D, plot_path, '数量', args, dfy2)
            dfb = df_D            
        elif args.O_geo and args.D_geo and args.rev0 == 'both':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt0 == '样方密度图':
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\OD去向分布_'+O_name+'.csv'
            df_O.to_csv(args.out_OD+filename, encoding='UTF-8', index=False) #导出表格
            plot_path = args.out_OD+'\\OD去向分布地_'+O_name+'.jpg'
            args.title = 'OD去向分布(O点:'+O_name+' D点:'+D_name+')'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '数量', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '数量', args, dfy)
            
            temp = D_intersect(df, dfy)
            df_D = temp
            if '深圳' not in D_name:
                df_D = O_intersect(temp, dfy2)
            elif args.pt0 == '样方密度图':
                df_D = OD_plot(temp, dfy2, 'D') #转换描点范围
            filename = '\OD来源分布_'+O_name+'.csv'
            plot_path = args.out_OD+'\\OD来源分布地_'+O_name+'.jpg'
            args.title = 'OD来源分布(O点:'+D_name+' D点:'+O_name+')'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy2, df_D, plot_path, '数量', args, dfy)
            else:           
                export_plot(dfy2, df_D, plot_path, '数量', args, dfy)
            dfb = df_D
        else:
            dfb = df
            filename = '\OD分析'+str(df['日期'].iloc[0])+'_wgs84.csv'
        dfb.to_csv(args.out_OD+filename, encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_OD)
        print('==============================================================')
    elif args.num_OD and args.replot:
        print('分析类型:OD数量（重新出图）')
        args.cellsize = args.ODcellsize
        if args.D_geo and args.rev0 == '以分析范围为起点':
            df, dfy = OD_reload_point(args.num_OD, args.D_geo, 'O')
            if args.O_geo:
                dfy2 = gpd.read_file(args.O_geo)
                O_name = parse_path(args.O_geo)
                D_name = parse_path(args.D_geo)
                args.title = 'OD去向分布(O点:'+O_name+' D点:'+D_name+')'
            else:
                dfy2 = ''
                args.title = 'OD去向分布'
            plot_path = args.out_OD+'\\OD去向分布(新)_'+O_name+'.jpg'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '数量', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '数量', args, dfy2)
        elif args.O_geo and args.rev0 == '以分析范围为终点':
            df, dfy = OD_reload_point(args.num_OD, args.O_geo, 'D')
            if args.D_geo:
                dfy2 = gpd.read_file(args.D_geo)
                O_name = parse_path(args.O_geo)
                D_name = parse_path(args.D_geo)
                args.title = 'OD来源分布(O点:'+O_name+' D点:'+D_name+')'
            else:
                dfy2 = ''
                args.title = 'OD来源分布'
            plot_path = args.out_OD+'\\OD来源分布(新)_'+D_name+'.jpg'
            if args.pt0 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '数量', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '数量', args, dfy2)
        print('图像已成功保存至', args.out_OD)
        print('==============================================================')
        
    #通勤数量
    if args.num_lw and not args.replot:
        filename = '\通勤数量.csv'
        print('分析类型:通勤数量')
        args.cellsize = args.ODcellsize
        df, dfy, dfy2 = read_OD(args.num_lw, args.num_live_geo, args.num_work_geo)
        O_name = parse_path(args.num_live_geo)
        D_name = parse_path(args.num_work_geo)
        print('文件读取完成!')
        if args.wgs:
            df = livework_to_wgs(df)
            print('坐标转换完成!')
        if args.num_live_geo and args.num_work_geo and args.rev1 == '以分析范围为居住地':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt1 == '样方密度图':                
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\居住人口通勤数量_'+O_name+'.csv'
            plot_path = args.out_num_lw+'\\居住人口工作地分布_'+O_name+'.jpg'
            args.title = '居住人口工作地分布(居住地:'+O_name+' 工作地:'+D_name+')'
            dfb = df_O
            dfb.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False)
            if args.pt1 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '人数', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '人数', args, dfy)
        elif args.num_live_geo and args.num_work_geo and args.rev1 == '以分析范围为工作地':
            temp = D_intersect(df, dfy2)
            df_D = temp
            if '深圳' not in O_name:
                df_D = O_intersect(temp, dfy)
            elif args.pt1 == '样方密度图':
                df_D = OD_plot(temp, dfy, 'D') #转换描点范围
            filename = '\就业人口通勤数量_'+D_name+'.csv'
            plot_path = args.out_num_lw+'\\就业人口居住地分布_'+D_name+'.jpg'
            args.title = '就业人口居住地分布(居住地:'+O_name+' 工作地:'+D_name+')'
            dfb = df_D
            dfb.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False)
            if args.pt1 == 'OD图':
                OD_Linestring(dfy, df_D, plot_path, '人数', args, dfy2)
            else:
                export_plot(dfy, df_D, plot_path, '人数', args, dfy2)
        elif args.num_live_geo and args.num_work_geo and args.rev1 == 'both':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt1 == '样方密度图':
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\居住人口通勤数量_'+O_name+'.csv'
            df_O.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False) #导出表格
            plot_path = args.out_num_lw+'\\居住人口工作地分布_'+O_name+'.jpg'
            args.title = '居住人口工作地分布(居住地:'+O_name+' 工作地:'+D_name+')'
            if args.pt1 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '人数', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '人数', args, dfy)
            
            temp = D_intersect(df, dfy)
            df_D = temp
            if '深圳' not in D_name:
                df_D = O_intersect(temp, dfy2)
            elif args.pt1 == '样方密度图':
                df_D = OD_plot(temp, dfy2, 'D') #转换描点范围
            filename = '\就业人口通勤数量_'+O_name+'.csv'
            plot_path = args.out_num_lw+'\\就业人口居住地分布_'+O_name+'.jpg'
            args.title = '就业人口居住地分布(居住地:'+D_name+' 工作地:'+O_name+')'
            dfb = df_D
            dfb.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False)
            if args.pt1 == 'OD图':
                OD_Linestring(dfy2, df_D, plot_path, '人数', args, dfy)
            else:
                export_plot(dfy2, df_D, plot_path, '人数', args, dfy)
        else:
            dfb = df
            filename = '\通勤数量'+str(df['日期'].iloc[0])+'_wgs84.csv'
            dfb.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False)
        #dfb.to_csv(args.out_num_lw+filename, encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_num_lw)
        print('==============================================================')
    elif args.num_lw and args.replot:
        print('分析类型:通勤数量（重新出图）')
        args.cellsize = args.ODcellsize
        if args.num_work_geo and args.rev1 == '以分析范围为居住地':
            df, dfy = OD_reload_point(args.num_lw, args.num_work_geo, 'O')
            if args.num_live_geo:
                dfy2 = gpd.read_file(args.num_live_geo)
                O_name = parse_path(args.num_live_geo)
                D_name = parse_path(args.num_work_geo)
                args.title = '居住人口工作地分布(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                dfy2 = ''
                args.title = '居住人口工作地分布'
            plot_path = args.out_num_lw+'\\居住人口工作地分布(新)_'+O_name+'.jpg'
            if args.pt1 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '人数', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '人数', args, dfy2)
        elif args.num_live_geo and args.rev1 == '以分析范围为工作地':
            df, dfy = OD_reload_point(args.num_lw, args.num_live_geo, 'D')
            if args.num_work_geo:
                dfy2 = gpd.read_file(args.num_work_geo)
                O_name = parse_path(args.num_live_geo)
                D_name = parse_path(args.num_work_geo)
                args.title = '就业人口居住地分布(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                dfy2 = ''
                args.title = '就业人口居住地分布'
            plot_path = args.out_num_lw+'\\就业人口居住地分布(新)_'+D_name+'.jpg'
            if args.pt1 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '人数', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '人数', args, dfy2)
        print('图像已成功保存至', args.out_num_lw)
        print('==============================================================')
        
    #通勤时间
    if args.time_lw and not args.replot:
        filename = '\通勤时间.csv'
        print('分析类型:通勤时间')
        args.cellsize = args.ODcellsize
        df, dfy, dfy2 = read_OD(args.time_lw, args.time_live_geo, args.time_work_geo)
        O_name = parse_path(args.time_live_geo)
        D_name = parse_path(args.time_work_geo)
        print('文件读取完成!')
        if args.wgs:
            df = livework_to_wgs(df)
            print('坐标转换完成!')
        df['平均通勤时间(min)'] = df['平均通勤时间(s)']/60
        if args.time_merge and args.opt10:
            df = merge_time(args.time_merge, df)
            df = df[df['人数']>=int(args.vmin)] #按最小值筛选
            print('通勤数量合并完成!')
        if args.time_live_geo and args.time_work_geo and args.rev2 == '以分析范围为居住地':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt2 == '样方密度图':
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\居住人口通勤时间_'+O_name+'.csv'
            plot_path = args.out_time_lw+'\\居住人口通勤时间分布_'+O_name+'.jpg'
            args.title = '居住人口工作地及通勤时间分布(居住地:'+O_name+' 工作地:'+D_name+')'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '平均通勤时间(min)', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '平均通勤时间(min)', args, dfy)
            dfb = df_O            
        elif args.time_live_geo and args.time_work_geo and args.rev2 == '以分析范围为工作地':
            temp = D_intersect(df, dfy2)
            df_D = temp
            if '深圳' not in O_name:
                df_D = O_intersect(temp, dfy)
            elif args.pt2 == '样方密度图':
                df_D = OD_plot(temp, dfy, 'D') #转换描点范围
            filename = '\就业人口通勤时间_'+D_name+'.csv'
            plot_path = args.out_time_lw+'\\就业人口通勤时间分布_'+D_name+'.jpg'
            args.title = '就业人口居住地及通勤时间分布(居住地:'+O_name+' 工作地:'+D_name+')'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy, df_D, plot_path, '平均通勤时间(min)', args, dfy2)
            else:
                export_plot(dfy, df_D, plot_path, '平均通勤时间(min)', args, dfy2)
            dfb = df_D
        elif args.time_live_geo and args.time_work_geo and args.rev2 == 'both':
            temp = O_intersect(df, dfy)
            df_O = temp
            if '深圳' not in D_name:
                df_O = D_intersect(temp, dfy2)
            elif args.pt2 == '样方密度图':
                df_O = OD_plot(temp, dfy2, 'O') #转换描点范围
            filename = '\居住人口通勤时间_'+O_name+'.csv'
            df_O.to_csv(args.out_time_lw+filename, encoding='UTF-8', index=False) #导出表格
            plot_path = args.out_time_lw+'\\居住人口通勤时间分布_'+O_name+'.jpg'
            args.title = '居住人口工作地及通勤时间分布(居住地:'+O_name+' 工作地:'+D_name+')'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy2, df_O, plot_path, '平均通勤时间(min)', args, dfy)
            else:
                export_plot(dfy2, df_O, plot_path, '平均通勤时间(min)', args, dfy)
            
            temp = D_intersect(df, dfy)
            df_D = temp
            if '深圳' not in D_name:
                df_D = O_intersect(temp, dfy2)
            elif args.pt2 == '样方密度图':
                df_D = OD_plot(temp, dfy2, 'D') #转换描点范围
            filename = '\就业人口通勤时间_'+O_name+'.csv'
            plot_path = args.out_time_lw+'\\就业人口通勤时间分布_'+O_name+'.jpg'
            args.title = '就业人口居住地及通勤时间分布(居住地:'+D_name+' 工作地:'+O_name+')'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy2, df_D, plot_path, '平均通勤时间(min)', args, dfy)
            else:
                export_plot(dfy2, df_D, plot_path, '平均通勤时间(min)', args, dfy)
            dfb = df_D
        else:
            dfb = df
            filename = '\通勤时间'+str(df['日期'].iloc[0])+'_wgs84.csv'
        dfb.to_csv(args.out_time_lw+filename, encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_time_lw)
        print('==============================================================')
    elif args.time_lw and args.replot:
        print('分析类型:通勤时间（重新出图）')
        args.cellsize = args.ODcellsize
        if args.time_work_geo and args.rev2 == '以分析范围为居住地':
            df, dfy = OD_reload_point(args.time_lw, args.time_work_geo, 'O')
            if args.time_live_geo:
                dfy2 = gpd.read_file(args.time_live_geo)
                O_name = parse_path(args.time_live_geo)
                D_name = parse_path(args.time_work_geo)
                args.title = '居住人口工作地及通勤时间分布(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                dfy2 = ''
                args.title = '居住人口工作地及通勤时间分布'
            plot_path = args.out_time_lw+'\\居住人口通勤时间分布(新)_'+O_name+'.jpg'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '平均通勤时间(min)', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '平均通勤时间(min)', args, dfy2)
        elif args.time_live_geo and args.rev2 == '以分析范围为工作地':
            df, dfy = OD_reload_point(args.time_lw, args.time_live_geo, 'D')
            if args.time_work_geo:
                dfy2 = gpd.read_file(args.time_work_geo)
                O_name = parse_path(args.time_live_geo)
                D_name = parse_path(args.time_work_geo)
                args.title = '就业人口居住地及通勤时间分布(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                dfy2 = ''
                args.title = '就业人口居住地及通勤时间分布'
            plot_path = args.out_time_lw+'\\就业人口通勤时间分布(新)_'+D_name+'.jpg'
            if args.pt2 == 'OD图':
                OD_Linestring(dfy, df, plot_path, '平均通勤时间(min)', args, dfy2)
            else:
                export_plot(dfy, df, plot_path, '平均通勤时间(min)', args, dfy2)
        print('图像已成功保存至', args.out_time_lw)
        print('==============================================================')
        
    #通勤方式
    if args.way_lw and not args.replot:
        filename = '\通勤方式.csv'
        print('分析类型:通勤方式')
        df, dfy, dfy2 = read_OD(args.way_lw, args.way_live_geo, args.way_work_geo)
        O_name = parse_path(args.way_live_geo)
        D_name = parse_path(args.way_work_geo)
        print('文件读取完成!')
        if args.wgs:
            df = livework_to_wgs(df)
            print('坐标转换完成!')
        if args.lw_merge and args.opt7:
            df = merge_lw(args.lw_merge, df)
            print('通勤数量合并完成!')
        if args.way_live_geo and args.rev3 == '以分析范围为居住地':
            dfb = O_intersect(df, dfy)
            if args.way_work_geo and '深圳' not in D_name:
                dfb = D_intersect(dfb, dfy2)
                args.title = '居住人口通勤方式(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '居住人口通勤方式(居住地:'+O_name+' 工作地:深圳市)'
            filename = '\居住人口通勤方式_'+O_name+'.csv'
            plot_path = args.out_way_lw+'\\居住人口通勤方式_'+O_name+'.jpg'
            commute_pie(dfb, plot_path, args)
        elif args.way_work_geo and args.rev3 == '以分析范围为工作地':
            dfb = D_intersect(df, dfy2)
            if args.way_live_geo and '深圳' not in O_name:
                dfb = O_intersect(dfb, dfy)
                args.title = '就业人口通勤方式(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '就业人口通勤方式(居住地:深圳市 工作地:'+D_name+')'
            filename = '\就业人口通勤方式_'+D_name+'.csv'
            plot_path = args.out_way_lw+'\\就业人口通勤方式_'+D_name+'.jpg'
            commute_pie(dfb, plot_path, args)
        elif args.way_live_geo and args.rev3 == 'both':
            temp = O_intersect(df, dfy)
            if args.way_work_geo and '深圳' not in D_name:
                temp = D_intersect(temp, dfy2)
                args.title = '居住人口通勤方式(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '居住人口通勤方式(居住地:'+O_name+' 工作地:深圳市)'
            filename = '\居住人口通勤方式_'+O_name+'.csv'
            temp.to_csv(args.out_way_lw+filename, encoding='UTF-8', index=False)
            plot_path = args.out_way_lw+'\\居住人口通勤方式_'+O_name+'.jpg'
            commute_pie(temp, plot_path, args)
            
            dfb = D_intersect(df, dfy)
            if args.way_work_geo and '深圳' not in D_name:
                dfb = O_intersect(dfb, dfy2)
                args.title = '就业人口通勤方式(居住地:'+D_name+' 工作地:'+O_name+')'
            else:
                args.title = '就业人口通勤方式(居住地:深圳市 工作地:'+O_name+')'
            filename = '\就业人口通勤方式_'+O_name+'.csv'
            plot_path = args.out_way_lw+'\\就业人口通勤方式_'+O_name+'.jpg'
            commute_pie(dfb, plot_path, args)
        else:
            dfb = df
            filename = '\通勤方式'+str(df['日期'].iloc[0])+'_wgs84.csv'
        dfb.to_csv(args.out_way_lw+filename, encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_way_lw)
        print('==============================================================')
    elif args.way_lw and args.replot:
        print('分析类型:通勤方式（重新出图）')
        df = pd.read_csv(args.way_lw)
        if args.rev3 == '以分析范围为居住地':
            plot_path = args.out_way_lw+'\\居住人口通勤方式(新).jpg'
            args.title = '居住人口通勤方式'
            commute_pie(df, plot_path, args)        
        elif args.rev3 == '以分析范围为工作地':
            plot_path = args.out_way_lw+'\\就业人口通勤方式(新).jpg'
            args.title = '就业人口通勤方式'
            commute_pie(df, plot_path, args)
        print('图像已成功保存至', args.out_way_lw)
        print('==============================================================')
        
    #职住画像
    if args.por_lw and not args.replot:
        filename = '\职住画像.csv'
        print('分析类型:职住画像')
        df, dfy, dfy2 = read_OD(args.por_lw, args.por_live_geo, args.por_work_geo)
        O_name = parse_path(args.por_live_geo)
        D_name = parse_path(args.por_work_geo)
        print('文件读取完成!')
        if args.wgs:
            df = livework_to_wgs(df)
            print('坐标转换完成!')
        if args.lw_por_merge and args.opt8:
            df = por_merge(args.lw_por_merge, df)
            print('通勤数量合并完成!')
        if args.por_live_geo and args.rev4 == '以分析范围为居住地':
            dfb = O_intersect(df, dfy)
            if args.por_work_geo and '深圳' not in D_name:
                dfb = D_intersect(dfb, dfy2)
                args.title = '居住人口通勤画像(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '居住人口通勤画像(居住地:'+O_name+' 工作地:深圳市)'                
            filename = '\职住画像_居住_'+O_name+'.csv'
            plot_path = args.out_por_lw+'\\职住画像_居住_'+O_name+'.jpg'
            export_pie(dfb, plot_path, args)
        elif args.por_work_geo and args.rev4 == '以分析范围为工作地':
            dfb = D_intersect(df, dfy2)
            if args.por_live_geo and '深圳' not in O_name:
                dfb = O_intersect(dfb, dfy)
                args.title = '就业人口通勤画像(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '就业人口通勤画像(居住地:深圳市 工作地:'+D_name+')'                
            filename = '\职住画像_就业_'+D_name+'.csv'
            plot_path = args.out_por_lw+'\\职住画像_就业_'+D_name+'.jpg'
            export_pie(dfb, plot_path, args)
        elif args.por_live_geo and args.rev4 == 'both':
            temp = O_intersect(df, dfy)
            if args.por_work_geo and '深圳' not in D_name:
                temp = D_intersect(temp, dfy2)
                args.title = '居住人口通勤画像(居住地:'+O_name+' 工作地:'+D_name+')'
            else:
                args.title = '居住人口通勤画像(居住地:'+O_name+' 工作地:深圳市)'                
            filename = '\职住画像_居住_'+O_name+'.csv'
            temp.to_csv(args.out_por_lw+filename, encoding='UTF-8', index=False)
            plot_path = args.out_por_lw+'\\职住画像_居住_'+O_name+'.jpg'
            export_pie(temp, plot_path, args)
            
            dfb = D_intersect(df, dfy)
            if args.por_work_geo and '深圳' not in D_name:
                dfb = O_intersect(dfb, dfy2)
                args.title = '就业人口通勤画像(居住地:'+D_name+' 工作地:'+O_name+')'
            else:
                args.title = '就业人口通勤画像(居住地:深圳市 工作地:'+O_name+')'                
            filename = '\职住画像_就业_'+O_name+'.csv'
            plot_path = args.out_por_lw+'\\职住画像_就业_'+O_name+'.jpg'
            export_pie(dfb, plot_path, args)
        else:
            dfb = df
            filename = '\职住画像'+str(df['日期'].iloc[0])+'_wgs84.csv'
        dfb.to_csv(args.out_por_lw+filename, encoding='UTF-8', index=False)
        print('文件已成功保存至', args.out_por_lw)
        print('==============================================================')
    elif args.por_lw and args.replot:
        print('分析类型:职住画像（重新出图）')
        df = pd.read_csv(args.por_lw)
        if args.rev4 == '以分析范围为居住地':
            plot_path = args.out_por_lw+'\\职住画像_居住(新).jpg'
            args.title = '居住人口通勤画像'
            export_pie(df, plot_path, args)        
        elif args.rev4 == '以分析范围为工作地':
            plot_path = args.out_por_lw+'\\职住画像_就业(新).jpg'
            args.title = '就业人口通勤画像'
            export_pie(df, plot_path, args)
        print('图像已成功保存至', args.out_por_lw)
        print('==============================================================')

# *** 通用函数 *** #
# 只转坐标
def grab_and_go(data):
    df = pd.read_csv(data, sep="\t")
    df = to_wgs(df)
    return df

# 只出图
def reload_point(data, geofile):
    df = pd.read_csv(data)
    dfy = gpd.read_file(geofile)
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['x'], df['y']))
    dfx.crs = 'EPSG:4490' #按地理坐标系读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        dfx = dfx.to_crs(epsg=4547) #转投影坐标
        dfy = dfy.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        dfx = dfx.to_crs(epsg=4526) #转投影坐标
        dfy = dfy.to_crs(epsg=4526) #转投影坐标
    return dfx, dfy

# OD只出图
def OD_reload_point(data, geofile, signal):
    df = pd.read_csv(data)
    dfy = gpd.read_file(geofile)
    if signal == 'O':
        df_reverse = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['D_x'], df['D_y']))
    elif signal == 'D':
        df_reverse = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['O_x'], df['O_y'])) 
    df_reverse.crs = 'EPSG:4490' #按WGS84读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        df_reverse = df_reverse.to_crs(epsg=4547) #转投影坐标
        df_reverse = df_reverse.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        df_reverse = df_reverse.to_crs(epsg=4526) #转投影坐标
        df_reverse = df_reverse.to_crs(epsg=4526) #转投影坐标
    return df_reverse, dfy

# 从文件路径提取范围名称
def parse_path(path):
    if path is not None:
        path = path.split('\\')
        temp = path[len(path)-1]
        temp = temp.split('.')
        name = temp[0]
        return name

def read_file(data, geofile='name'):
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
        dfy = None
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
    date = df['日期'].iloc[0]
    df = df.groupby(['网格ID','网格中心x坐标','网格中心y坐标','x','y']).aggregate({'人数': 'sum'}).reset_index()
    df['日期'] = date
    return df

def intersect(df, dfy):
    print('正在执行空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['x'], df['y']))
    dfx.crs = 'EPSG:4490' #按地理坐标系读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        dfx = dfx.to_crs(epsg=4547) #转投影坐标
        dfy = dfy.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        dfx = dfx.to_crs(epsg=4526) #转投影坐标
        dfy = dfy.to_crs(epsg=4526) #转投影坐标

    if dfx.columns.__contains__('index_right'):
        dfx.drop(['index_right'], axis=1, inplace=True)
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    return dfb    
    
#客流画像专用    
def merge_num(num, df):
    print('正在合并客流数量...')
    if num.__contains__('.txt'):
        dfnum = pd.read_csv(num, sep="\t")
        dfnum.drop(columns=['网格中心x坐标','网格中心y坐标'],inplace=True)
    else:
        dfnum = pd.read_csv(num)
        dfnum.drop(columns=['网格中心x坐标','网格中心y坐标','x','y'],inplace=True)
    df.drop(columns=['网格中心x坐标','网格中心y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    
    if df.columns.__contains__('小时'):
        df_final = pd.merge(df, dfnum, on = ['日期','小时','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 3:51].mul(df_final.人数, 0))
    else:
        df_final = pd.merge(df, dfnum, on = ['日期','网格ID'], how = 'outer')
        df_final.update(df_final.iloc[:, 2:50].mul(df_final.人数, 0))
    return df_final

#常住数量专用
def merge_longstay(df, args):
    if args.num_without1 and args.num_without2 and args.lw_ratio and args.opt3:
        print('正在计算居住且工作人口数量...')
        if args.num_without1.__contains__('.txt'):
            df2 = pd.read_csv(args.num_without1, sep="\t")
        else:
            df2 = pd.read_csv(args.num_without1)
            df2.drop(columns=['x','y'],inplace=True)   
        if args.num_without2.__contains__('.txt'):
            df3 = pd.read_csv(args.num_without2, sep="\t")
        else:
            df3 = pd.read_csv(args.num_without2)
            df3.drop(columns=['x','y'],inplace=True)
        if args.lw_ratio.__contains__('.txt'):
            df4 = pd.read_csv(args.lw_ratio, sep="\t")
        else:
            df4 = pd.read_csv(args.lw_ratio)
            df4.drop(columns=['x','y'],inplace=True)
         
        if df['人口类型'].iloc[0] == 'home':
            if (df2['人口类型'].iloc[0] == 'liveWithoutWork') and (df3['人口类型'].iloc[0] == 'workWithoutLive'):
                df2.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','居住不工作人数']
                df2.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df3.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','工作不居住人数']
                df3.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df4.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','工作人数']
                df4.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)

                dfs = [df,df2,df3,df4]
                df_final = reduce(lambda left,right: pd.merge(left,right,on=['日期','区域名称','网格ID'],how = "outer"), dfs)
                df_final.fillna(value=0, inplace=True)
                df_final['居住且工作人数'] = (df_final['人数']+df_final['工作人数']-df_final['居住不工作人数']-df_final['工作不居住人数'])/2
                df_final['居住人数'] = df_final['人数']
        elif df['人口类型'].iloc[0] == 'work':
            if (df2['人口类型'].iloc[0] == 'workWithoutLive') and (df3['人口类型'].iloc[0] == 'liveWithoutWork'):
                df2.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','工作不居住人数']
                df2.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df3.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','居住不工作人数']
                df3.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                df4.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','居住人数']
                df4.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
                
                dfs = [df,df2,df3,df4]
                df_final = reduce(lambda left,right: pd.merge(left,right,on=['日期','区域名称','网格ID'],how = "outer"), dfs)
                df_final.fillna(value=0, inplace=True)
                df_final['居住且工作人数'] = (df_final['人数']+df_final['居住人数']-df_final['居住不工作人数']-df_final['工作不居住人数'])/2
                df_final['工作人数'] = df_final['人数']
        df_final.drop(columns=['网格x坐标','网格y坐标','人口类型','人数'],inplace=True)
        print('居住且工作人口计算完成!')
    else:
        df_final = df
    if args.lw_ratio and args.opt4:
        if args.lw_ratio.__contains__('.txt'):
            df3 = pd.read_csv(args.lw_ratio, sep="\t")
        else:
            df3 = pd.read_csv(args.lw_ratio)
            df3.drop(columns=['x','y'],inplace=True)
        temp_name = df3['人口类型'].iloc[0]
        df3.drop(columns=['网格x坐标','网格y坐标','人口类型'],inplace=True)
        df3.columns = ['日期','区域名称','网格ID',temp_name]
        df_final = pd.merge(df_final, df3, on = ['日期','区域名称','网格ID'], how = "outer")
        if df_final.columns.__contains__('人数') and df_final.columns.__contains__('home'):
            df_final.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','work','x','y','home']
        elif df_final.columns.__contains__('人数') and df_final.columns.__contains__('work'):
            df_final.columns = ['日期','区域名称','网格ID','网格x坐标','网格y坐标','人口类型','home','x','y','work']
    return df_final

def calc_ratio(df):
    print('正在计算职住比...')
    if df.columns.__contains__('居住人数'):
        ratio = df['work'].sum()/df['居住人数'].sum()
    elif df.columns.__contains__('工作人数'):
        ratio = df['工作人数'].sum()/df['home'].sum()
    else:
        ratio = df['work'].sum()/df['home'].sum()
    print('分析范围内职住比为:', ratio)

#常住画像专用
def merge_res(num, df):
    print('正在合并常住数量...')
    if num.__contains__('.txt'):
        dfnum = pd.read_csv(num, sep="\t")
        dfnum.drop(columns=['网格x坐标','网格y坐标'],inplace=True)
    else:
        dfnum = pd.read_csv(num)
        dfnum.drop(columns=['网格x坐标','网格y坐标','x','y'],inplace=True)
    
    df.drop(columns=['网格x坐标','网格y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
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
    elif data.__contains__('.csv'):
        df = pd.read_csv(data)
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
    date = df['日期'].iloc[0]
    #起点范围
    if args.O_geo and not args.D_geo:
        df = df.groupby(['起点区域名称','终点区域名称','网格ID','起点网格中心x坐标','起点网格中心y坐标','O_x','O_y']).aggregate({'数量': 'sum'}).reset_index()
    #终点范围
    elif args.D_geo and not args.O_geo:
        df = df.groupby(['起点区域名称','终点区域名称','网格ID','终点网格中心x坐标','终点网格中心y坐标','D_x','D_y']).aggregate({'数量': 'sum'}).reset_index()
    #两个范围
    elif args.O_geo and args.D_geo:
        df = df.groupby(['起点区域名称','终点区域名称','起点网格ID','终点网格ID','起点网格中心x坐标','起点网格中心y坐标','终点网格中心x坐标','终点网格中心y坐标','O_x','O_y','D_x','D_y']).aggregate({'数量': 'sum'}).reset_index()
    df['日期'] = date
    return df

def O_intersect(df, dfy):
    print('正在执行起点范围空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['O_x'], df['O_y']))
    if dfx.columns.__contains__('index_left'):
        dfx.drop(['index_left'], axis=1, inplace=True)
    dfx.crs = 'EPSG:4490' #按WGS84读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114') :
        dfx = dfx.to_crs(epsg=4547) #转投影坐标
        dfy = dfy.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        dfx = dfx.to_crs(epsg=4526) #转投影坐标
        dfy = dfy.to_crs(epsg=4526) #转投影坐标
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    if dfb.columns.__contains__('index_right'):
        dfb.drop(['index_right'], axis=1, inplace=True)
    return dfb

def D_intersect(df, dfy):
    print('正在执行终点范围空间相交...')
    dfx = gpd.GeoDataFrame(df, geometry = gpd.points_from_xy(df['D_x'], df['D_y']))
    dfx.crs = 'EPSG:4490' #按WGS84读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        dfx = dfx.to_crs(epsg=4547) #转投影坐标
        dfy = dfy.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        dfx = dfx.to_crs(epsg=4526) #转投影坐标
        dfy = dfy.to_crs(epsg=4526) #转投影坐标
    dfb = gpd.sjoin(dfx, dfy, op='intersects') #执行相交
    if dfb.columns.__contains__('index_right'):
        dfb.drop(['index_right'], axis=1, inplace=True)
    return dfb

def OD_plot(dfb, dfy, signal):
    if signal == 'O':
        df_reverse = gpd.GeoDataFrame(dfb, geometry = gpd.points_from_xy(dfb['D_x'], dfb['D_y']))
    elif signal == 'D':
        df_reverse = gpd.GeoDataFrame(dfb, geometry = gpd.points_from_xy(dfb['O_x'], dfb['O_y']))
    df_reverse.crs = 'EPSG:4490' #按WGS84读取
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        df_reverse = df_reverse.to_crs(epsg=4547) #转投影坐标
        df_reverse = df_reverse.to_crs(epsg=4547) #转投影坐标
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        df_reverse = df_reverse.to_crs(epsg=4526) #转投影坐标
        df_reverse = df_reverse.to_crs(epsg=4526) #转投影坐标
    return df_reverse

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

def merge_time(num, df):
    print('正在合并通勤数量...')
    if num.__contains__('.txt'):
        dfnum = pd.read_csv(num, sep="\t")
    else:
        dfnum = pd.read_csv(num)
        dfnum.drop(columns=['O_x','O_y','D_x','D_y'], inplace=True)
    df_final = pd.merge(df, dfnum, on = ['日期','居住地名称','起点网格ID','居住地网格中心x坐标','居住地网格中心y坐标','工作地名称','终点网格ID','工作地网格中心x坐标','工作地网格中心y坐标'], how = 'outer')
    return df_final

def merge_lw(num, df):
    print('正在合并通勤数量...')
    if num.__contains__('.txt'):
        dfnum = pd.read_csv(num, sep="\t")
    else:
        dfnum = pd.read_csv(num)
        dfnum.drop(columns=['O_x','O_y','D_x','D_y'], inplace=True)

    df_final = pd.merge(df, dfnum, on = ['日期','居住地名称','起点网格ID','居住地网格中心x坐标','居住地网格中心y坐标','工作地名称','终点网格ID','工作地网格中心x坐标','工作地网格中心y坐标'], how = 'outer')
    df_final.update(df_final.iloc[:, 9:14].mul(df_final.人数, 0))
    return df_final

def por_merge(num, df):
    print('正在合并通勤数量...')
    if num.__contains__('.txt'):
        dfnum = pd.read_csv(num, sep="\t")
        dfnum.drop(columns=['居住地网格中心x坐标','居住地网格中心y坐标','工作地网格中心x坐标','工作地网格中心y坐标'],inplace=True)
    else:
        dfnum = pd.read_csv(num)
        dfnum.drop(columns=['居住地网格中心x坐标','居住地网格中心y坐标','工作地网格中心x坐标','工作地网格中心y坐标','O_x','O_y','D_x','D_y'],inplace=True)

    df.drop(columns=['居住地网格中心x坐标','居住地网格中心y坐标','工作地网格中心x坐标','工作地网格中心y坐标','消费水平:低','消费水平:中','消费水平:高','人生阶段:初中生','人生阶段:高中生','人生阶段:大学生','人生阶段:研究生','人生阶段:孕期','人生阶段:育儿阶段','人生阶段:家有孕妇','人生阶段:家有0-1岁小孩','人生阶段:家有1-3岁小孩','人生阶段:家有3-6岁小孩','人生阶段:家有小学生','人生阶段:家有初中生','人生阶段:家有高中生'],inplace=True)
    df_final = pd.merge(df, dfnum, on = ['日期','居住地名称','起点网格ID','工作地名称','终点网格ID'], how = 'outer')
    df_final.update(df_final.iloc[:, 5:53].mul(df_final.人数, 0))
    return df_final

def export_plot(dfy, dfb, plot_path, variable, args, AOI=None):
    print('正在绘图中...')
    #参数转换为数值
    if args.cellsize != '自定义范围':
        args.cellsize = int(args.cellsize)
    args.vmin = int(args.vmin)
    args.k = int(args.k)
    args.alpha = float(args.alpha)
    if args.cmap == 'Dense_20':
        args.cmap = Dense_20.mpl_colormap
    if dfb.columns.__contains__('index_right'):
        del dfb['index_right']
    #坐标系
    if str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger CM 114'):
        sys_proj = 4547
    elif str(dfy.crs).__contains__('CGCS2000 / 3-degree Gauss-Kruger zone 38'):
        sys_proj = 4526
    else:
        sys_proj = 4547
    #加载底图
    ###
    
    fig = plt.figure(figsize=(14, 8))
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.epsg(sys_proj))
    
    #x0, x1, y0, y1
    ax.set_extent([dfy['geometry'].total_bounds[0]-600, dfy['geometry'].total_bounds[2]+600, dfy['geometry'].total_bounds[1]-600, dfy['geometry'].total_bounds[3]+600], crs=ccrs.epsg(sys_proj))

    if args.basemap == '天地图矢量':
        request = TDT_vec()
    elif args.basemap == '天地图影像':
        request = TDT_img()
    elif args.basemap == 'Mapbox(首选key)':
        request = MB_vec_default()
    elif args.basemap == 'Mapbox(备选key)':
        request = MB_vec_backup()
    ax.add_image(request, 15)
    plt.suptitle(args.title, fontsize=18) #最高级别标题
    
    ###
    if args.cellsize == '自定义范围':
        if plot_path.__contains__('居住人口样方密度') or plot_path.__contains__('就业人口样方密度'):
            pops = int(dfb[variable].sum())
            area = round((dfy.area/10**6).sum(),2)
            density = round(pops/area,2)
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+'  统计口径：自定义范围\n总人数：'+str(pops)+' 范围面积：'+str(area)+'平方公里 人口密度：'+str(density)+'人/平方公里'
        elif dfb.columns.__contains__('小时'):
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+' '+str(dfb['小时'].iloc[0])+'时  统计口径：自定义范围'
        else:
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+'  统计口径：自定义范围'
        plt.title(subtitle, fontsize=15) #副标题
        jiedao = gpd.read_file(args.custom)
        dfo = gpd.sjoin(jiedao, dfb, op='contains')
        
    else:
        if plot_path.__contains__('居住人口样方密度') or plot_path.__contains__('就业人口样方密度'):
            pops = int(dfb[variable].sum())
            area = round((dfy.area/10**6).sum(),2)
            density = round(pops/area,2)
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+'  网格大小：'+str(args.cellsize)+'米x'+str(args.cellsize)+'米\n总人数：'+str(pops)+' 范围面积：'+str(area)+'平方公里 人口密度：'+str(density)+'人/平方公里'
        elif dfb.columns.__contains__('小时'):
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+' '+str(dfb['小时'].iloc[0])+'时  网格大小：'+str(args.cellsize)+'米x'+str(args.cellsize)+'米'
        else:
            subtitle = '时间：'+str(dfb['日期'].iloc[0])+'  网格大小：'+str(args.cellsize)+'米x'+str(args.cellsize)+'米'
        plt.title(subtitle, fontsize=15) #副标题
        
        if args.cellsize == 100:
            #绘制泰森多边形
            dfy = dfy.dissolve()
            coords = points_to_coords(dfb.geometry)
            area_shape = dfy.iloc[0].geometry
            region_polys, region_pts = voronoi_regions_from_coords(coords, area_shape)
            voro_polys = gpd.GeoDataFrame(geometry=list(region_polys.values()), crs='epsg:4547')
            if dfb.columns.__contains__('index_right'):
                del dfb['index_right']
            dfo = gpd.sjoin(voro_polys, dfb, op='contains') #泰森多边形与dfb空间相交
        else:
            #绘制渔网图
            coord1 = (dfy['geometry'].total_bounds[0]-100, dfy['geometry'].total_bounds[3]+100)
            coord3 = (dfy['geometry'].total_bounds[2]+100, dfy['geometry'].total_bounds[1]-100)
            coord2 = (coord3[0],coord1[1])
            coord4 = (coord1[0],coord3[1])
            rectangle = Polygon([coord1,coord2,coord3,coord4])
            rectangle = gpd.GeoDataFrame([rectangle],columns=['geometry'])
            rectangle = rectangle.set_crs(epsg=sys_proj)
            coords = rectangle['geometry'].bounds.values[0]
            loc_all = '{},{},{},{}'.format(coords[0],coords[3],coords[2],coords[1])
            nets = lng_lat(loc_all, args.cellsize)
            netfish = gpd.GeoDataFrame([getPolygon(i[0],i[1]) for i in nets],columns=['geometry'])
            netfish = netfish.set_crs(epsg=sys_proj)
            netfish = netfish.reset_index()
            dfo = gpd.sjoin(netfish, dfb, op='contains') #渔网与dfb空间相交

    #合并网格
    if args.cellsize != 100:
        dfo = dfo.reset_index()
        if dfo.columns.__contains__('平均通勤时间(min)'):
            df_index = dfo.groupby(['index']).aggregate({variable: 'mean'})
        else:
            df_index = dfo.groupby(['index']).aggregate({variable: 'sum'})
        del dfo[variable]
        dfo = pd.merge(dfo, df_index, how='inner', on='index')
        dfo.drop_duplicates(subset=['index'], keep='first', inplace=True)
        
    #通勤时间
    if dfo.columns.__contains__('平均通勤时间(min)'):
        args.scheme = 'user_defined'
        args.userbin = '15,30,45,60'
    else:
        dfo = dfo[dfo[variable]>=args.vmin] #按最小值筛选
    
    path = plot_path.split('.jpg', 1)[0]
    dfo.to_csv(path+'.csv', index=False, encoding='ANSI')
    
    ###
    
    #绘制OD分析范围
    if AOI is not None: 
        AOI = AOI.to_crs(epsg=sys_proj)
        AOI.boundary.plot(ax=ax, linestyle='-', edgecolor='k', zorder=3)
    #绘制样方密度图
    dfy.boundary.plot(ax=ax, linestyle='--', edgecolor='grey', zorder=2) #绘制范围
    if args.scheme == 'user_defined':
        temp = args.userbin.split(',')
        results = list(map(int, temp))
        dfo.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, classification_kwds={'bins': results}, alpha=args.alpha, zorder=1)
    else:
        dfo.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, k=args.k, alpha=args.alpha, zorder=1)
    #自定义图例
    handles, labels = ax.get_legend_handles_labels()
    cmap = plt.get_cmap(args.cmap)
    if args.scheme == 'natural_breaks':
        nb = mc.NaturalBreaks(dfo[variable], k=args.k)
    elif args.scheme == 'equal_interval':
        nb = mc.EqualInterval(dfo[variable], k=args.k)
    elif args.scheme == 'fisher_jenks':
        nb = mc.FisherJenks(dfo[variable], k=args.k)
    elif args.scheme == 'jenks_caspall':
        nb = mc.JenksCaspall(dfo[variable], k=args.k)
    elif args.scheme == 'quantiles':
        nb = mc.Quantiles(dfo[variable], k=args.k)
    elif args.scheme == 'user_defined':
        nb = mc.UserDefined(dfo[variable], bins=results)
    bins = nb.bins
    coef = 1/(args.k-1)
    LegendElement = [mpatches.Patch(facecolor=cmap(0), label=f'{args.vmin} - {int(bins[0])}')] + [mpatches.Patch(facecolor=cmap(_*coef), label=f'{int(bins[_-1])} - {int(bins[_])}') for _ in range(1,args.k)]
    ax.legend(handles = LegendElement, bbox_to_anchor=(1,0), loc='lower left', fontsize=10, title=variable, shadow=False)
    ax.axis('off')
    fig.savefig(plot_path, dpi=400)
    
    ###

def export_pie(dfb, plot_path, args):
    print('正在绘图中...')
    fig, axs = plt.subplots(2, 2)
    plt.suptitle(args.title, fontsize=18) #最高级别标题
    #性别
    gender_total = dfb['性别:男'].sum() + dfb['性别:女'].sum()
    gender_label = ['男', '女']
    gender_value = [dfb['性别:男'].sum()/gender_total, dfb['性别:女'].sum()/gender_total]
    gender_color = ['#96BFFF','#9FE6B8']
    axs[0, 0].pie(gender_value, labels=gender_label, colors=gender_color, autopct='%.f%%', shadow=False, counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 1}, startangle=90)
    axs[0, 0].set_title('性别比例', fontsize=14)
    #年龄
    if dfb.columns.__contains__('人口类型') or dfb.columns.__contains__('居住地名称'):
        age_total = dfb['年龄阶段:18-24'].sum() + dfb['年龄阶段:25-34'].sum() + dfb['年龄阶段:35-44'].sum() + dfb['年龄阶段:45-54'].sum() + dfb['年龄阶段:55-64'].sum() + dfb['年龄阶段:65以上'].sum()
        age_value = [(dfb['年龄阶段:18-24'].sum()+dfb['年龄阶段:25-34'].sum())/age_total, (dfb['年龄阶段:35-44'].sum()+dfb['年龄阶段:45-54'].sum())/age_total, (dfb['年龄阶段:55-64'].sum()+dfb['年龄阶段:65以上'].sum())/age_total]
    else:
        age_total = dfb['年龄:18-24'].sum() + dfb['年龄:25-34'].sum() + dfb['年龄:35-44'].sum() + dfb['年龄:45-54'].sum() + dfb['年龄:55-64'].sum() + dfb['年龄:65以上'].sum()
        age_value = [(dfb['年龄:18-24'].sum()+dfb['年龄:25-34'].sum())/age_total, (dfb['年龄:35-44'].sum()+dfb['年龄:45-54'].sum())/age_total, (dfb['年龄:55-64'].sum()+dfb['年龄:65以上'].sum())/age_total]
    age_label = ['18-34岁', '35-54岁', '55岁及以上']
    age_color = ['#37A2DA','#32C5E9','#67E0E3']
    axs[0, 1].pie(age_value, labels=age_label, colors=age_color, autopct='%.f%%', shadow=False, counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 1}, startangle=90)
    axs[0, 1].set_title('年龄结构', fontsize=14)
    #教育
    edu_total = dfb['教育水平:高中及以下'].sum() + dfb['教育水平:大专'].sum() + dfb['教育水平:本科及以上'].sum()
    edu_label = ['高中及以下', '大专', '本科及以上']
    edu_value = [dfb['教育水平:高中及以下'].sum()/edu_total, dfb['教育水平:大专'].sum()/edu_total, dfb['教育水平:本科及以上'].sum()/edu_total]
    edu_color = ['#FFDB5C','#ff9f7f','#fb7293']
    axs[1, 0].pie(edu_value, labels=edu_label, colors=edu_color, autopct='%.f%%', shadow=False, counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 1}, startangle=90)
    axs[1, 0].set_title('教育水平', fontsize=14)
    #收入
    income_total = dfb['收入水平:2499及以下'].sum() + dfb['收入水平:2500~3999'].sum() + dfb['收入水平:4000~7999'].sum() + dfb['收入水平:8000~19999'].sum() + dfb['收入水平:20000及以上'].sum()
    income_label = ['4000元以下', '4000-7999元', '8000-19999元', '20000元及以上']
    income_value = [(dfb['收入水平:2499及以下'].sum()+dfb['收入水平:2500~3999'].sum())/income_total, dfb['收入水平:4000~7999'].sum()/income_total, dfb['收入水平:8000~19999'].sum()/income_total, dfb['收入水平:20000及以上'].sum()/income_total]
    income_color = ['#e7bcf3','#E690D1','#9d96f5','#8378EA']
    axs[1, 1].pie(income_value, labels=income_label, colors=income_color, autopct='%.f%%', shadow=False, counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 1}, startangle=90)
    axs[1, 1].set_title('收入水平', fontsize=14)
    plt.tight_layout()
    fig.savefig(plot_path, dpi=400)
    
def commute_pie(dfb, plot_path, args):
    print('正在绘图中...')
    fig = plt.figure(figsize=(6, 6))
    plt.title(args.title, fontsize=15)
    total = dfb['驾车比例'].sum() + dfb['地铁比例'].sum() + dfb['公交比例'].sum() + dfb['骑行比例'].sum() + dfb['步行比例'].sum()
    label = ['驾车', '地铁', '公交', '骑行', '步行']
    value = [dfb['驾车比例'].sum()/total, dfb['地铁比例'].sum()/total, dfb['公交比例'].sum()/total, dfb['骑行比例'].sum()/total, dfb['步行比例'].sum()/total]
    color = ['#9FE6B8','#32C5E9','#fb7293','#e7bcf3','#9d96f5']
    plt.pie(value, labels=label, colors=color, autopct='%.f%%', shadow=False, counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 1}, startangle=90)
    plt.tight_layout()
    fig.savefig(plot_path, dpi=400)
    
def OD_Linestring(dfy, dfb, plot_path, variable, args, AOI=None):
    print('正在绘图中...')
    #坐标转线段
    oddata = gpd.GeoDataFrame(dfb)
    r = oddata.iloc[0]
    oddata['geometry']=oddata.apply(lambda r:LineString([[r['O_x'],r['O_y']],[r['D_x'],r['D_y']]]),axis = 1)
    #参数转换为数值
    args.vmin = int(args.vmin)
    args.k = int(args.k)
    args.alpha = float(args.alpha)
    args.linewidth = float(args.linewidth)
    dfy = dfy.to_crs(epsg=4326)
    if args.cmap == 'Dense_20':
        args.cmap = Dense_20.mpl_colormap
    if dfb.columns.__contains__('index_right'):
        del dfb['index_right']
    #加载图框
    fig = plt.figure(figsize=(12, 8))
    ax = plt.subplot(111)
    ax.set_xlim(dfy.total_bounds[0]-0.05,dfy.total_bounds[2]+0.05)
    ax.set_ylim(dfy.total_bounds[1]-0.05,dfy.total_bounds[3]+0.05)
    plt.suptitle(args.title, fontsize=18) #最高级别标题
    subtitle = '时间：'+str(dfb['日期'].iloc[0])
    plt.title(subtitle, fontsize=15) #副标题        
    #绘制OD分析范围
    if AOI is not None: 
        AOI = AOI.to_crs(epsg=4326)
        AOI.boundary.plot(ax=ax, linestyle='-', edgecolor='k', zorder=3)
    #绘制OD
    dfy.boundary.plot(ax=ax, linestyle='--', edgecolor='grey', zorder=2) #绘制范围
    if dfb.columns.__contains__('平均通勤时间(min)'):
        args.scheme = 'user_defined'
        args.userbin = '15,30,45,60'
        temp = args.userbin.split(',')
        results = list(map(int, temp))
        args.vmin = 1
        dfb.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, linewidth = args.linewidth*(dfb['人数']/dfb['人数'].max()), classification_kwds={'bins': results}, alpha=args.alpha, zorder=1)
    elif args.scheme == 'user_defined':
        temp = args.userbin.split(',')
        results = list(map(int, temp))
        dfb = dfb[dfb[variable]>=args.vmin] #按最小值筛选
        dfb.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, linewidth = args.linewidth*(dfb[variable]/dfb[variable].max()), classification_kwds={'bins': results}, alpha=args.alpha, zorder=1)
    else:
        dfb = dfb[dfb[variable]>=args.vmin] #按最小值筛选
        dfb.plot(column=variable, ax=ax, cmap=args.cmap, scheme=args.scheme, linewidth = args.linewidth*(dfb[variable]/dfb[variable].max()), k=args.k, alpha=args.alpha, zorder=1)
    #自定义图例
    handles, labels = ax.get_legend_handles_labels()
    cmap = plt.get_cmap(args.cmap)
    if args.scheme == 'natural_breaks':
        nb = mc.NaturalBreaks(dfb[variable], k=args.k)
    elif args.scheme == 'equal_interval':
        nb = mc.EqualInterval(dfb[variable], k=args.k)
    elif args.scheme == 'fisher_jenks':
        nb = mc.FisherJenks(dfb[variable], k=args.k)
    elif args.scheme == 'jenks_caspall':
        nb = mc.JenksCaspall(dfb[variable], k=args.k)
    elif args.scheme == 'quantiles':
        nb = mc.Quantiles(dfb[variable], k=args.k)
    elif args.scheme == 'user_defined':
        nb = mc.UserDefined(dfb[variable], bins=results)
    bins = nb.bins
    coef = 1/(args.k-1)
    LegendElement = [mpatches.Patch(facecolor=cmap(0), label=f'{args.vmin} - {int(bins[0])}')] + [mpatches.Patch(facecolor=cmap(_*coef), label=f'{int(bins[_-1])} - {int(bins[_])}') for _ in range(1,args.k)]
    ax.legend(handles = LegendElement, bbox_to_anchor=(1,0), loc='lower left', fontsize=10, title=variable, shadow=False)
    ax.axis('off')
    fig.savefig(plot_path, dpi=400)

def pic_to_gif(paths, outpath):
    ims = []
    for i in range(len(paths)):
        temp = Image.open(paths[i])
        ims.append(temp)
    ims[0].save(outpath, save_all=True, append_images=ims, duration=600, loop=0)

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
