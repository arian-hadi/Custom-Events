from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.safestring import mark_safe

from accounts.models import CustomUser


class EditorTitle(models.Model):
    """Model for customizable editor titles with rarity tiers"""
    
    RARITY_CHOICES = [
        ('ordinary', 'Ordinary'),
        ('epic', 'Epic'),
        ('legendary', 'Legendary'),
    ]
    
    CATEGORY_CHOICES = [
        ('reel', 'Reel Title'),
        ('comment', 'Comment Title'),
        ('general', 'General Title'),
    ]
    
    name = models.CharField(max_length=100, unique=True, help_text="Title name (e.g., 'Ultimate Editing Master')")
    rarity = models.CharField(max_length=20, choices=RARITY_CHOICES, default='ordinary')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general', help_text="Category of the title (reel, comment, or general)")
    description = models.TextField(blank=True, help_text="Description of the title")
    cost_coins = models.IntegerField(default=0, help_text="Cost in coins to unlock (0 = free/unlocked by default)")
    is_default = models.BooleanField(default=False, help_text="Default title for new users")
    is_active = models.BooleanField(default=True, help_text="Whether this title is available")
    unlock_requirement = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Requirement to unlock (e.g., 'Win 10 Edit of the Week', 'Reach 1000 followers')"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'rarity', 'cost_coins', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_rarity_display()})"
    
    def get_rarity_color_class(self):
        """Return CSS class for rarity color"""
        colors = {
            'ordinary': 'text-gray-600',
            'epic': 'text-purple-600',
            'legendary': 'text-yellow-500',
        }
        return colors.get(self.rarity, 'text-gray-600')
    
    def get_rarity_bg_class(self):
        """Return CSS class for rarity background"""
        colors = {
            'ordinary': 'bg-gray-100',
            'epic': 'bg-purple-100',
            'legendary': 'bg-yellow-100',
        }
        return colors.get(self.rarity, 'bg-gray-100')


class EditorApplication(models.Model):
    """Model for editor applications to the EditingHub ranking table"""
    
    CHANNEL_TYPE_CHOICES = [
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
    ]
    
    EDITING_TOOL_CHOICES = [
        ('after_effects', 'After Effects'),
        ('alight_motion', 'Alight Motion'),
        ('capcut', 'CapCut'),
        ('other', 'Other')
    ]

    EDITING_TOOL_SVG_MAP = {
        'after_effects': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 240 234" xmlns="http://www.w3.org/2000/svg">
    <title>After Effects</title>
    <style type="text/css">.st0{fill:#00005B;}.st1{fill:#9999FF;}</style>
    <g>
        <path class="st0" d="M42.5,0h155C221,0,240,19,240,42.5v149c0,23.5-19,42.5-42.5,42.5h-155C19,234,0,215,0,191.5v-149C0,19,19,0,42.5,0z"/>
        <path class="st1" d="M96.4,140H59.2l-7.6,23.6c-0.2,0.9-1,1.5-1.9,1.4H31c-1.1,0-1.4-0.6-1.1-1.8l32.2-92.3c0.3-1,0.6-1.9,1-3.1c0.4-2.1,0.6-4.3,0.6-6.5c-0.1-0.5,0.3-1,0.8-1.1h25.9c0.7,0,1.2,0.3,1.3,0.8l36.5,102c0.3,1.1,0,1.6-1,1.6h-20.9c-0.7,0.1-1.4-0.4-1.6-1.1L96.4,140z M65,120.1h25.4c-0.6-2.1-1.4-4.6-2.3-7.2c-0.9-2.7-1.8-5.6-2.7-8.6c-1-3.1-1.9-6.1-2.9-9.2s-1.9-6-2.7-8.9c-0.8-2.8-1.5-5.4-2.2-7.8h-0.2c-0.9,4.3-2,8.6-3.4,12.9c-1.5,4.8-3,9.8-4.6,14.8C68.1,111.2,66.5,115.8,65,120.1z"/>
        <path class="st1" d="M187,131h-31.7c0.4,3.1,1.4,6.2,3.1,8.9c1.8,2.7,4.3,4.8,7.3,6c4,1.7,8.4,2.6,12.8,2.5c3.5-0.1,7-0.4,10.4-1.1c3.1-0.4,6.1-1.2,8.9-2.3c0.5-0.4,0.8-0.2,0.8,0.8v15.3c0,0.4-0.1,0.8-0.2,1.2c-0.2,0.3-0.4,0.5-0.7,0.7c-3.2,1.4-6.5,2.4-10,3c-4.7,0.9-9.4,1.3-14.2,1.2c-7.6,0-14-1.2-19.2-3.5c-4.9-2.1-9.2-5.4-12.6-9.5c-3.2-3.9-5.5-8.3-6.9-13.1c-1.4-4.7-2.1-9.6-2.1-14.6c0-5.4,0.8-10.7,2.5-15.9c1.6-5,4.1-9.6,7.5-13.7c3.3-4,7.4-7.2,12.1-9.5s10.3-3.1,16.7-3.1c5.3-0.1,10.6,0.9,15.5,3.1c4.1,1.8,7.7,4.5,10.5,8c2.6,3.4,4.7,7.2,6,11.4c1.3,4,1.9,8.1,1.9,12.2c0,2.4-0.1,4.5-0.2,6.4c-0.2,1.9-0.3,3.3-0.4,4.2c-0.1,0.7-0.7,1.3-1.4,1.3C196.5,130.5,195.4,130.6,187,131z M155.3,116.4h21.1c2.6,0,4.5,0,5.7-0.1c0.8-0.1,1.6-0.3,2.3-0.8v-1c0-1.3-0.2-2.5-0.6-3.7c-1.8-5.6-7.1-9.4-13-9.2c-5.5-0.3-10.7,2.6-13.3,7.6C156.3,111.5,155.6,114,155.3,116.4z"/>
    </g>
</svg>''',
        'alight_motion': '''<svg class="h-15 w-15" aria-hidden="true" viewBox="0 0 3840 2160" xmlns="http://www.w3.org/2000/svg" style="shape-rendering:geometricPrecision; text-rendering:geometricPrecision; image-rendering:optimizeQuality; fill-rule:evenodd; clip-rule:evenodd" xmlns:xlink="http://www.w3.org/1999/xlink">
    <title>Alight Motion</title>
    <g><path style="opacity:1" fill="#162339" d="M 1328.5,70.5 C 1722.17,70.3333 2115.83,70.5 2509.5,71C 2609.97,81.3788 2698.3,119.712 2774.5,186C 2864.64,268.452 2915.81,370.619 2928,492.5C 2928.67,884.5 2928.67,1276.5 2928,1668.5C 2916.11,1783.78 2868.61,1881.95 2785.5,1963C 2703.24,2039.4 2606.41,2081.23 2495,2088.5C 2116.69,2087.18 1739.52,2087.18 1363.5,2088.5C 1229.01,2084.67 1116.51,2033 1026,1933.5C 958.302,1855.12 920.468,1764.79 912.5,1662.5C 911.169,1468.25 910.502,1273.91 910.5,1079.5C 910.667,885.833 910.833,692.167 911,498.5C 923.228,365.223 981.061,255.723 1084.5,170C 1122.29,140.868 1163.12,117.368 1207,99.5C 1208.87,100.089 1210.54,99.4224 1212,97.5C 1212.33,97.8333 1212.67,98.1667 1213,98.5C 1237.79,88.9054 1263.29,81.7388 1289.5,77C 1302.68,75.0485 1315.68,72.8819 1328.5,70.5 Z"/></g>
    <g><path style="opacity:1" fill="#16a47d" d="M 1964.5,430.5 C 1963.18,430.33 1962.01,430.663 1961,431.5C 1953.86,430.817 1946.7,430.15 1939.5,429.5C 1926.37,429.521 1913.37,429.521 1900.5,429.5C 1919.06,428.759 1936.56,428.425 1953,428.5C 1956.94,429.138 1960.77,429.804 1964.5,430.5 Z"/></g>
    <g><path style="opacity:1" fill="#15a77f" d="M 1897.5,429.5 C 1891.83,430.833 1886.17,430.833 1880.5,429.5C 1886.86,428.892 1892.53,428.892 1897.5,429.5 Z"/></g>
    <g><path style="opacity:1" fill="#02fbaa" d="M 1880.5,429.5 C 1886.17,430.833 1891.83,430.833 1897.5,429.5C 1898.5,429.5 1899.5,429.5 1900.5,429.5C 1913.37,429.521 1926.37,429.521 1939.5,429.5C 1946.7,430.15 1953.86,430.817 1961,431.5C 1962.01,430.663 1963.18,430.33 1964.5,430.5C 1966.3,430.065 1968.3,430.065 1970.5,430.5C 1973.62,431.479 1976.96,431.813 1980.5,431.5C 1981.5,431.5 1982.5,431.5 1983.5,431.5C 1986.05,432.388 1988.72,432.721 1991.5,432.5C 1996.66,432.442 2001.49,432.442 2006,432.5C 2008.32,433.845 2010.66,434.178 2013,433.5C 2019.84,434.446 2026.84,435.779 2034,437.5C 2034.41,437.043 2034.91,436.709 2035.5,436.5C 2038.72,437.665 2041.88,438.665 2045,439.5C 2046.96,438.146 2048.96,438.479 2051,440.5C 2074.53,443.822 2098.36,449.155 2122.5,456.5C 2123.77,456.43 2124.94,456.097 2126,455.5C 2127.75,458.338 2130.09,459.005 2133,457.5C 2138.36,461.83 2144.36,463.83 2151,463.5C 2152.59,465.808 2154.59,466.475 2157,465.5C 2158.34,467.605 2160,468.271 2162,467.5C 2163.68,469.701 2165.68,470.367 2168,469.5C 2174.95,472.489 2181.95,475.489 2189,478.5C 2343.95,539.025 2466.78,641.358 2557.5,785.5C 2588.1,836.584 2612.1,890.584 2629.5,947.5C 2629.74,951.479 2630.74,955.146 2632.5,958.5C 2652,1025.19 2661.17,1093.19 2660,1162.5C 2655.18,1181.32 2643.18,1192.65 2624,1196.5C 2606.89,1196.68 2593.89,1188.34 2585,1171.5C 2584.01,1168.58 2583.35,1165.58 2583,1162.5C 2582.59,1075.34 2566.25,989.339 2534,904.5C 2525.95,886.233 2517.78,868.067 2509.5,850C 2479.62,792.982 2443.29,740.816 2400.5,693.5C 2399.17,690.833 2397.17,688.833 2394.5,687.5C 2388.45,679.782 2381.78,672.782 2374.5,666.5C 2373.09,664.086 2371.09,662.419 2368.5,661.5C 2359.36,651.822 2349.69,643.322 2339.5,636C 2336.42,630.921 2332.08,627.254 2326.5,625C 2319.79,618.626 2312.79,612.626 2305.5,607C 2297.41,601.922 2289.58,596.422 2282,590.5C 2281.67,590.833 2281.33,591.167 2281,591.5C 2276.81,586.805 2272.14,583.472 2267,581.5C 2257.58,574.404 2247.91,567.737 2238,561.5C 2236.98,562.634 2236.32,562.301 2236,560.5C 2233.47,559.499 2230.64,558.166 2227.5,556.5C 2226.91,556.709 2226.41,557.043 2226,557.5C 2223.28,553.311 2219.61,551.311 2215,551.5C 2214.3,550.309 2213.47,549.309 2212.5,548.5C 2211.09,546.461 2209.09,545.461 2206.5,545.5C 2205.29,543.324 2203.62,542.991 2201.5,544.5C 2200.31,543.147 2198.98,541.98 2197.5,541C 2185.6,534.88 2173.94,529.214 2162.5,524C 2149.82,519.761 2137.49,514.928 2125.5,509.5C 2123.9,507.926 2121.9,507.259 2119.5,507.5C 2117.15,505.615 2114.65,505.282 2112,506.5C 2108.33,504.833 2104.67,503.167 2101,501.5C 2099.44,502.345 2098.44,501.679 2098,499.5C 2095.95,499.848 2093.95,499.181 2092,497.5C 2091.67,497.833 2091.33,498.167 2091,498.5C 2087.93,497.751 2084.93,496.751 2082,495.5C 2081.67,495.833 2081.33,496.167 2081,496.5C 2077.9,495.724 2074.74,494.39 2071.5,492.5C 2068.09,490.926 2064.43,489.926 2060.5,489.5C 2056.84,489.631 2053.17,488.631 2049.5,486.5C 2048.09,487.668 2046.93,487.335 2046,485.5C 2044,485.5 2042,485.5 2040,485.5C 2038.92,483.606 2037.59,483.273 2036,484.5C 2028.52,482.464 2021.02,480.464 2013.5,478.5C 2011.69,479.859 2010.19,479.525 2009,477.5C 2008.33,480.167 2007.67,480.167 2007,477.5C 2006.67,477.833 2006.33,478.167 2006,478.5C 2004.92,476.606 2003.59,476.273 2002,477.5C 1993.58,476.014 1985.41,474.347 1977.5,472.5C 1976.68,474.748 1975.68,474.914 1974.5,473C 1970.14,472.89 1965.98,472.057 1962,470.5C 1960.41,472.285 1958.91,472.452 1957.5,471C 1954.57,470.223 1951.74,470.39 1949,471.5C 1941.69,470.047 1934.36,468.714 1927,467.5C 1918.48,467.882 1908.98,467.882 1898.5,467.5C 1894.17,466.167 1889.83,466.167 1885.5,467.5C 1882.97,466.939 1880.47,466.606 1878,466.5C 1866.62,467.249 1855.45,467.916 1844.5,468.5C 1842.5,467.167 1840.5,467.167 1838.5,468.5C 1836.04,468.208 1833.38,468.208 1830.5,468.5C 1828.37,467.458 1826.37,467.792 1824.5,469.5C 1821.79,469.737 1819.29,469.737 1817,469.5C 1815.48,471.202 1813.48,471.535 1811,470.5C 1809.34,470.675 1808.01,471.342 1807,472.5C 1804.04,470.923 1801.38,471.256 1799,473.5C 1798.33,472.833 1797.67,472.167 1797,471.5C 1796.26,472.641 1795.43,472.641 1794.5,471.5C 1785.98,473.131 1777.48,474.797 1769,476.5C 1766.73,475.405 1764.56,475.739 1762.5,477.5C 1760.55,476.897 1758.55,477.23 1756.5,478.5C 1754.66,477.808 1752.83,478.142 1751,479.5C 1749.98,478.366 1749.32,478.699 1749,480.5C 1745.4,479.764 1742.07,479.764 1739,480.5C 1737.92,482.394 1736.59,482.727 1735,481.5C 1715.52,486.16 1697.02,490.827 1679.5,495.5C 1677.34,495.766 1675.67,496.766 1674.5,498.5C 1673.71,498.069 1672.87,497.735 1672,497.5C 1668.28,498.427 1664.94,500.094 1662,502.5C 1658.86,501.863 1655.86,502.529 1653,504.5C 1652.67,504.167 1652.33,503.833 1652,503.5C 1651.58,504.672 1650.91,505.672 1650,506.5C 1648.61,505.446 1647.11,505.28 1645.5,506C 1640.87,507.992 1636.2,509.992 1631.5,512C 1630.37,514.21 1628.87,514.71 1627,513.5C 1625.35,513.82 1624.35,514.82 1624,516.5C 1621.55,514.987 1619.88,515.654 1619,518.5C 1618.67,518.167 1618.33,517.833 1618,517.5C 1605.31,521.517 1593.31,526.851 1582,533.5C 1581.28,532.549 1580.45,532.383 1579.5,533C 1572.45,537.861 1564.45,541.861 1555.5,545C 1550.3,547.758 1545.14,551.258 1540,555.5C 1538.28,554.448 1537.28,555.114 1537,557.5C 1535.61,556.446 1534.11,556.28 1532.5,557C 1471.37,593.552 1414.87,638.385 1363,691.5C 1349.02,706.825 1335.52,722.492 1322.5,738.5C 1318.87,741.139 1315.87,744.472 1313.5,748.5C 1313.58,749.93 1313.25,751.264 1312.5,752.5C 1309.8,754.707 1307.63,757.374 1306,760.5C 1305.67,760.167 1305.33,759.833 1305,759.5C 1302.89,763.281 1300.39,766.781 1297.5,770C 1297.96,770.414 1298.29,770.914 1298.5,771.5C 1294.17,773.872 1293.34,772.539 1296,767.5C 1310.04,746.908 1324.7,726.241 1340,705.5C 1353.3,690.364 1366.46,675.031 1379.5,659.5C 1388.52,651.146 1397.19,642.479 1405.5,633.5C 1407.75,632.92 1409.42,631.587 1410.5,629.5C 1416.95,623.573 1423.28,617.406 1429.5,611C 1432.27,610.729 1433.94,609.229 1434.5,606.5C 1435.74,605.754 1437.07,605.421 1438.5,605.5C 1438.28,604.325 1438.61,603.325 1439.5,602.5C 1446.79,598.725 1453.13,593.558 1458.5,587C 1469.34,580.072 1479.68,572.406 1489.5,564C 1497.12,560.231 1503.95,556.064 1510,551.5C 1575.37,507.89 1645.87,475.89 1721.5,455.5C 1724.23,455.829 1726.56,455.163 1728.5,453.5C 1745.92,448.547 1763.08,444.88 1780,442.5C 1781,441.833 1782,441.167 1783,440.5C 1786.12,439.603 1789.12,439.603 1792,440.5C 1793.71,439.237 1795.37,438.903 1797,439.5C 1798.33,438.833 1799.67,438.167 1801,437.5C 1802.78,438.536 1804.61,438.536 1806.5,437.5C 1810.44,438.602 1814.1,437.935 1817.5,435.5C 1830,433.757 1842.67,432.424 1855.5,431.5C 1857.83,432.833 1860.17,432.833 1862.5,431.5C 1865.39,430.992 1868.22,430.325 1871,429.5C 1874.48,429.793 1877.65,429.793 1880.5,429.5 Z"/></g>
</svg>''',
        'capcut': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 512 510" xmlns="http://www.w3.org/2000/svg">
    <title>CapCut</title>
    <path fill="#ffffff" d="M116.971 2.475h278.058c62.971 0 114.494 51.522 114.494 114.494v275.722c0 62.971-51.523 114.493-114.494 114.493H116.971c-62.972 0-114.494-51.522-114.494-114.493V116.969c0-62.972 51.522-114.494 114.494-114.494z"/>
    <path fill="#999999" fill-rule="nonzero" d="M116.97 0h278.06C459.366 0 512 52.634 512 116.969v275.722c0 64.335-52.634 116.969-116.97 116.969H116.97C52.636 509.66 0 457.026 0 392.691V116.969C0 52.633 52.636 0 116.97 0zm278.06 4.952H116.97C55.364 4.952 4.953 55.363 4.953 116.969v275.723c0 61.605 50.411 112.016 112.017 112.016h278.06c61.607 0 112.017-50.41 112.017-112.016V116.969c0-61.607-50.41-112.017-112.017-112.017z"/>
    <path fill="#000000" fill-rule="nonzero" d="M109.095 181.505c2.223-19.532 18.316-34.578 37.955-35.483l167.194-.001a40.612 40.612 0 0130.095 17.427 42.152 42.152 0 016.39 14.915l49.135-24.364a2.185 2.185 0 013.141 1.674v27.628l.001.096a4.571 4.571 0 01-2.837 4.229 177620.936 177620.936 0 00-135.63 67.336l135.324 66.948a4.695 4.695 0 013.142 4.08v27.685a2.266 2.266 0 01-3.613 1.821c-16.12-8.162-32.464-15.854-48.462-24.18a63.503 63.503 0 01-4.282 11.225 40.813 40.813 0 01-26.098 20.135 44.994 44.994 0 01-11.221.919l-155.833.003c-3.51 0-7.04 0-10.53-.266-18.089-2.705-32.049-17.363-33.869-35.565v-26.77a5.935 5.935 0 014.08-4.879c27.791-13.732 55.521-27.587 83.353-41.258a32412.61 32412.61 0 00-84.17-41.748 5.41 5.41 0 01-3.223-4.918c-.042-8.876-.185-17.792-.042-26.689zm30.975.184c-1.674 3.367-.898 7.263-1.041 10.896 30.608 15.12 60.99 30.321 91.536 45.339 30.185-14.963 60.384-29.927 90.596-44.89 0-2.714.123-5.428 0-8.162a10.203 10.203 0 00-10.096-8.734h-.106l-161.565.001a10.082 10.082 0 00-9.345 5.55h.021zm-1.041 135.406c.142 3.673-.654 7.631 1.122 11.039a10.204 10.204 0 009.284 5.405l161.667.002.081-.001c3.618 0 6.961-1.94 8.754-5.081 2.04-3.57 1.102-7.855 1.305-11.773-30.26-14.936-60.48-30.118-90.801-44.89a43915.126 43915.126 0 00-91.432 45.299h.02z"/>
</svg>''',
        'other': '''<svg class="h-8 w-8" aria-hidden="true" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <title>Other</title>
    <circle cx="12" cy="12" r="10" fill="#4B5563" opacity="0.2"/>
    <path d="M12 6a1 1 0 011 1v4h3a1 1 0 010 2h-3v4a1 1 0 01-2 0v-4H8a1 1 0 110-2h3V7a1 1 0 011-1z" fill="#4B5563"/>
</svg>'''
    }

    EDITING_AREA_CHOICES = [
        ('transformers', 'Transformers'),
        ('dc', 'DC'),
        ('marvel', 'Marvel'),
        ('anime', 'Anime'),
        ('all', 'All'),
        ('others', 'Others'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='editor_applications'
    )
    
    # Channel information
    channel_link = models.URLField(max_length=500, help_text="YouTube or TikTok channel URL")
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    channel_name = models.CharField(max_length=200, blank=True, help_text="Fetched from channel")
    channel_thumbnail = models.URLField(max_length=500, blank=True, help_text="Channel thumbnail URL")
    follower_count = models.BigIntegerField(default=0, help_text="Follower/subscriber count")
    
    # Application details
    editing_area = models.CharField(max_length=50, choices=EDITING_AREA_CHOICES)
    editing_area_other = models.CharField(max_length=200, blank=True, help_text="If 'others' is selected")
    editing_tool = models.CharField(max_length=50, choices=EDITING_TOOL_CHOICES, default='other')
    
    # Verification and consent
    channel_verified = models.BooleanField(default=False, help_text="User confirmed this is their channel")
    data_consent = models.BooleanField(default=False, help_text="User consented to data usage")
    channel_screenshot = models.ImageField(
        upload_to='editinghub_screenshots/', 
        blank=True, 
        null=True,
        help_text="Screenshot of the channel page to verify ownership"
    )
    
    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    reviewed_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        limit_choices_to={'role': 'admin'}
    )
    
    # Ranking position (calculated based on follower count)
    rank_position = models.IntegerField(null=True, blank=True, help_text="Position in ranking table")
    rank_position_last_week = models.IntegerField(null=True, blank=True, help_text="Last week's position for trend arrows")
    rank_snapshot_at = models.DateTimeField(null=True, blank=True, help_text="When last weekly rank snapshot was taken")
    
    # User can request removal
    removal_requested = models.BooleanField(default=False)
    removal_requested_date = models.DateTimeField(null=True, blank=True)
    
    # Custom editor title
    selected_title = models.ForeignKey(
        'EditorTitle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applications',
        help_text="Selected custom editor title"
    )
    
    class Meta:
        ordering = ['-follower_count', 'applied_date']
        unique_together = ('user', 'channel_link')  # One application per user per channel
        
    def __str__(self):
        return f"{self.user.username} - {self.channel_name or self.channel_link} ({self.get_status_display()})"
    
    @staticmethod
    def update_rank_positions():
        """Update rank positions for all accepted applications based on follower count"""
        # Get all accepted applications ordered by follower count
        accepted_apps = EditorApplication.objects.filter(
            status='accepted',
            removal_requested=False
        ).order_by('-follower_count', 'applied_date')
        
        from django.utils import timezone
        now = timezone.now()
        for index, app in enumerate(accepted_apps, start=1):
            # Roll last week's snapshot if a week has passed or snapshot missing
            take_snapshot = False
            if app.rank_snapshot_at is None:
                take_snapshot = True
            else:
                try:
                    delta_days = (now - app.rank_snapshot_at).days
                    if delta_days >= 7:
                        take_snapshot = True
                except Exception:
                    take_snapshot = True

            if take_snapshot and app.rank_position is not None:
                app.rank_position_last_week = app.rank_position
                app.rank_snapshot_at = now

            app.rank_position = index
            app.save(update_fields=['rank_position', 'rank_position_last_week', 'rank_snapshot_at'])
    
    def update_rank_position(self):
        """Update rank position based on follower count - instance method for backward compatibility"""
        EditorApplication.update_rank_positions()
    
    def save(self, *args, **kwargs):
        """Override save to update rankings when status changes"""
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_obj = EditorApplication.objects.get(pk=self.pk)
                old_status = old_obj.status
            except EditorApplication.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update rankings if status changed to accepted or if this is a new accepted application
        if self.status == 'accepted' and (is_new or old_status != 'accepted'):
            EditorApplication.update_rank_positions()
            
            # Set user's profile picture from channel thumbnail if they don't have one
            if self.channel_thumbnail and not self.user.profile_picture:
                from .utils import download_image_from_url
                try:
                    downloaded_image = download_image_from_url(self.channel_thumbnail)
                    if downloaded_image:
                        self.user.profile_picture = downloaded_image
                        self.user.save(update_fields=['profile_picture'])
                except Exception as e:
                    # Log error but don't fail the save
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to download profile picture from {self.channel_thumbnail}: {e}")
        elif old_status == 'accepted' and self.status != 'accepted':
            # Recalculate all rankings if an accepted application changed status
            EditorApplication.update_rank_positions()

    @classmethod
    def editing_tool_choices_with_svg(cls):
        return [
            {
                'value': value,
                'label': label,
                'svg': cls.EDITING_TOOL_SVG_MAP.get(value, cls.EDITING_TOOL_SVG_MAP['other'])
            }
            for value, label in cls.EDITING_TOOL_CHOICES
        ]

    def editing_tool_icon(self):
        svg = self.EDITING_TOOL_SVG_MAP.get(self.editing_tool)
        if not svg:
            svg = self.EDITING_TOOL_SVG_MAP['other']
        return mark_safe(svg)

    def rank_delta(self):
        """Positive if moved up, negative if moved down, 0 if unchanged/unknown"""
        try:
            if self.rank_position is None or self.rank_position_last_week is None:
                return 0
            return self.rank_position_last_week - self.rank_position
        except Exception:
            return 0

    def rank_trend_icon(self):
        """HTML snippet for trend arrow: up (green), down (red), dash (gray)"""
        delta = self.rank_delta()
        if delta > 0:
            # Up arrow with delta value
            return mark_safe(f'<span title="+{delta}" class="ml-2 text-green-600" aria-label="rank up">▲</span>')
        if delta < 0:
            return mark_safe(f'<span title="{delta}" class="ml-2 text-red-600" aria-label="rank down">▼</span>')
        return mark_safe('<span class="ml-2 text-gray-400" aria-label="no change">–</span>')
    
    @property
    def editor_title(self):
        """Get the editor title - custom title if selected, otherwise default based on channel type"""
        if self.selected_title:
            return self.selected_title.name
        # Default title based on channel type
        return f"{self.channel_type.title()} Editor"
    
    @property
    def editor_title_rarity(self):
        """Get the rarity of the selected title"""
        if self.selected_title:
            return self.selected_title.rarity
        return 'ordinary'


class EditSubmission(models.Model):
    """Model for Edit of the Week submissions"""
    
    CHANNEL_TYPE_CHOICES = [
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_submissions'
    )
    
    # Link to approved EditorApplication (channel verification)
    approved_application = models.ForeignKey(
        EditorApplication,
        on_delete=models.CASCADE,
        related_name='edit_submissions',
        help_text="The approved EditorApplication that verifies this user's channel",
        null=True,
        blank=True  # Temporarily nullable for migration, will be made required after data migration
    )
    
    # Channel info (from approved application)
    channel_link = models.URLField(max_length=500, help_text="YouTube or TikTok channel URL (from approved application)")
    channel_type = models.CharField(max_length=20, choices=CHANNEL_TYPE_CHOICES)
    channel_name = models.CharField(max_length=200, blank=True)
    channel_thumbnail = models.URLField(max_length=500, blank=True)
    scheduled_week = models.DateField(
        null=True,
        blank=True,
        help_text="Monday (UTC) of the competition week this edit participates in"
    )
    
    # Edit information
    video_url = models.URLField(max_length=500, help_text="YouTube Shorts or TikTok video URL")
    direct_video_url = models.URLField(
        max_length=1000, 
        blank=True, 
        null=True,
        help_text="Direct video file URL (extracted via web scraping for TikTok, used for clean HTML5 video player)"
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    verified_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    upvote_count = models.IntegerField(default=0)
    report_count = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False, help_text="Featured in top 3 of the week")
    week_rank = models.IntegerField(null=True, blank=True, help_text="Rank in Edit of the Week (1-3)")
    
    # Video statistics (from platform APIs)
    views = models.BigIntegerField(default=0, help_text="Video views from platform")
    likes = models.BigIntegerField(default=0, help_text="Video likes from platform")
    comments = models.BigIntegerField(default=0, help_text="Video comments from platform")
    subscriber_count = models.BigIntegerField(default=0, help_text="Subscriber/follower count for normalization")
    
    # Points calculation
    calculated_points = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Total calculated points for ranking"
    )
    last_points_calculation = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Last time points were calculated"
    )
    weeks_participated = models.IntegerField(
        default=1,
        help_text="Number of consecutive weeks user has submitted edits"
    )
    
    class Meta:
        ordering = ['-calculated_points', '-submitted_date']
        
    def __str__(self):
        return f"{self.user.username} - {self.title or self.video_url} ({self.get_status_display()})"
    
    def update_upvote_count(self):
        """Update upvote count from related upvotes and recalculate points"""
        from django.utils import timezone
        from datetime import date
        
        self.upvote_count = self.upvotes.filter(is_active=True).count()
        
        # Only recalculate points if the scheduled week has started
        # Points should not be calculated for future week submissions
        today = date.today()
        if self.scheduled_week and self.scheduled_week <= today:
            # Recalculate points when upvotes change (upvotes contribute to points)
            self.calculated_points = self.calculate_points()
            self.save(update_fields=['upvote_count', 'calculated_points'])
        else:
            # Just update upvote count, don't calculate points yet
            self.save(update_fields=['upvote_count'])
    
    def update_report_count(self):
        """Update report count from related reports"""
        self.report_count = self.reports.filter(is_active=True).count()
        self.save(update_fields=['report_count'])
    
    def calculate_points(self):
        """
        Calculate total points based on platform performance and community feedback.
        Returns the calculated points value.
        """
        from .utils import calculate_youtube_points, calculate_tiktok_points
        
        # Base platform points
        if self.channel_type == 'youtube':
            platform_points = calculate_youtube_points(
                self.views, self.likes, self.comments, self.subscriber_count
            )
        elif self.channel_type == 'tiktok':
            platform_points = calculate_tiktok_points(
                self.views, self.likes, self.comments, self.subscriber_count
            )
        else:
            platform_points = 0.0
        
        # Upvote points (max 50)
        upvote_points = min(self.upvote_count * 2, 50)
        
        # Continuous participation bonus (15 pts per week)
        participation_points = (self.weeks_participated - 1) * 15
        
        # Total points
        total_points = platform_points + upvote_points + participation_points
        
        return float(total_points)


class EditUpvote(models.Model):
    """Model for tracking user upvotes on edits (max 3 per user)"""
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_upvotes'
    )
    
    edit_submission = models.ForeignKey(
        EditSubmission,
        on_delete=models.CASCADE,
        related_name='upvotes'
    )
    
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'edit_submission')
        ordering = ['-created_date']
    
    def __str__(self):
        return f"{self.user.username} upvoted {self.edit_submission}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.edit_submission.update_upvote_count()
    
    def delete(self, *args, **kwargs):
        edit_submission = self.edit_submission
        super().delete(*args, **kwargs)
        edit_submission.update_upvote_count()


class EditReport(models.Model):
    """Model for reporting explicit or inappropriate edits"""
    
    REPORT_REASON_CHOICES = [
        ('explicit', 'Explicit Content'),
        ('spam', 'Spam'),
        ('copyright', 'Copyright Violation'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='edit_reports'
    )
    
    edit_submission = models.ForeignKey(
        EditSubmission,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    
    reason = models.CharField(max_length=50, choices=REPORT_REASON_CHOICES)
    description = models.TextField(blank=True, help_text="Additional details")
    is_active = models.BooleanField(default=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_reports',
        limit_choices_to={'role': 'admin'}
    )
    resolved_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'edit_submission')
        ordering = ['-created_date']
    
    def __str__(self):
        return f"Report on {self.edit_submission} by {self.user.username} - {self.get_reason_display()}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.edit_submission.update_report_count()
    
    def delete(self, *args, **kwargs):
        edit_submission = self.edit_submission
        super().delete(*args, **kwargs)
        edit_submission.update_report_count()


# Signal to keep EditSubmission thumbnails in sync with EditorApplication
# This will be connected at the end of the file after EditSubmission is defined
def update_edit_submission_thumbnails_signal(sender, instance, **kwargs):
    """
    When EditorApplication thumbnail or channel_name is updated,
    automatically update all related EditSubmissions to keep them in sync.
    This ensures banner images always show the latest profile pictures.
    
    Uses fallback logic to prevent overwriting valid thumbnails with empty/invalid ones.
    """
    from .utils import is_valid_thumbnail_url, get_fallback_thumbnail
    
    # Only update if this is an accepted application
    if instance.status == 'accepted' and not instance.removal_requested:
        new_thumbnail = (instance.channel_thumbnail or '').strip()
        
        # Only proceed if the new thumbnail is valid, or if we need to update channel_name
        if is_valid_thumbnail_url(new_thumbnail) or instance.channel_name:
            # Get all EditSubmissions that reference this EditorApplication
            submissions_to_update = EditSubmission.objects.filter(
                approved_application=instance,
                status='verified'
            )
            
            # Update each submission individually to preserve existing valid thumbnails
            for submission in submissions_to_update:
                existing_thumbnail = (submission.channel_thumbnail or '').strip()
                # Use fallback to preserve existing valid thumbnails
                best_thumbnail = get_fallback_thumbnail(existing_thumbnail, new_thumbnail)
                
                submission.channel_thumbnail = best_thumbnail
                if instance.channel_name:
                    submission.channel_name = instance.channel_name
                submission.save(update_fields=['channel_thumbnail', 'channel_name'])
            
            # Also update EditSubmissions that don't have approved_application but match user/channel
            submissions_to_update_2 = EditSubmission.objects.filter(
                user=instance.user,
                channel_type=instance.channel_type,
                status='verified',
                approved_application__isnull=True
            )
            
            for submission in submissions_to_update_2:
                existing_thumbnail = (submission.channel_thumbnail or '').strip()
                # Use fallback to preserve existing valid thumbnails
                best_thumbnail = get_fallback_thumbnail(existing_thumbnail, new_thumbnail)
                
                submission.channel_thumbnail = best_thumbnail
                if instance.channel_name:
                    submission.channel_name = instance.channel_name
                submission.save(update_fields=['channel_thumbnail', 'channel_name'])

# Connect the signal after EditSubmission is defined
post_save.connect(update_edit_submission_thumbnails_signal, sender=EditorApplication)


class Tournament(models.Model):
    """Model for Tournament of Editors - Semi-Finals and Finals"""
    
    name = models.CharField(max_length=200, default="Tournament of Editors", help_text="Tournament name")
    is_active = models.BooleanField(default=True, help_text="Only one active tournament should exist")
    
    # Phase status
    semi_finals_active = models.BooleanField(default=True, help_text="Semi-finals phase is active")
    finals_active = models.BooleanField(default=False, help_text="Finals phase is active")
    
    # Semi-Final 1 participants
    participant_1 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_1',
        help_text="Semi-Final 1 - First participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_1_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for participant 1 (YouTube or TikTok URL)"
    )
    participant_2 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_2',
        help_text="Semi-Final 1 - Second participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_2_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for participant 2 (YouTube or TikTok URL)"
    )
    
    # Semi-Final 2 participants
    participant_3 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_3',
        help_text="Semi-Final 2 - First participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_3_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for participant 3 (YouTube or TikTok URL)"
    )
    participant_4 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_participant_4',
        help_text="Semi-Final 2 - Second participant",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    participant_4_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for participant 4 (YouTube or TikTok URL)"
    )
    
    # Finals participants (winners from semi-finals)
    finalist_1 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_finalist_1',
        help_text="Finalist 1 - Winner from Semi-Final 1 (left side)",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    finalist_1_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for finalist 1 (YouTube or TikTok URL)"
    )
    finalist_2 = models.ForeignKey(
        EditorApplication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tournament_finalist_2',
        help_text="Finalist 2 - Winner from Semi-Final 2 (right side)",
        limit_choices_to={'status': 'accepted', 'removal_requested': False}
    )
    finalist_2_edit_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Edit link for finalist 2 (YouTube or TikTok URL)"
    )
    
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_active', '-created_date']
        verbose_name = "Tournament"
        verbose_name_plural = "Tournaments"
    
    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"
    
    def get_participants(self):
        """Return list of semi-final participants in order"""
        return [
            self.participant_1,
            self.participant_2,
            self.participant_3,
            self.participant_4,
        ]
    
    def get_finalists(self):
        """Return list of finalists in order"""
        return [
            self.finalist_1,
            self.finalist_2,
        ]
    
    def save(self, *args, **kwargs):
        # If this tournament is being set as active, deactivate all others
        if self.is_active:
            Tournament.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_tournament(cls):
        """Get the currently active tournament"""
        return cls.objects.filter(is_active=True).first()
    
    def get_match_pairs(self):
        """Get match pairs for voting: [(participant_1, participant_2), (participant_3, participant_4), (finalist_1, finalist_2)]"""
        matches = []
        if self.semi_finals_active:
            if self.participant_1 and self.participant_2:
                matches.append({
                    'type': 'semi_final_1',
                    'participant_1': self.participant_1,
                    'participant_1_edit_link': self.participant_1_edit_link,
                    'participant_2': self.participant_2,
                    'participant_2_edit_link': self.participant_2_edit_link,
                })
            if self.participant_3 and self.participant_4:
                matches.append({
                    'type': 'semi_final_2',
                    'participant_1': self.participant_3,
                    'participant_1_edit_link': self.participant_3_edit_link,
                    'participant_2': self.participant_4,
                    'participant_2_edit_link': self.participant_4_edit_link,
                })
        if self.finals_active:
            if self.finalist_1 and self.finalist_2:
                matches.append({
                    'type': 'final',
                    'participant_1': self.finalist_1,
                    'participant_1_edit_link': self.finalist_1_edit_link,
                    'participant_2': self.finalist_2,
                    'participant_2_edit_link': self.finalist_2_edit_link,
                })
        return matches


class TournamentMatchVote(models.Model):
    """Model to track votes for tournament matches"""
    
    MATCH_TYPES = [
        ('semi_final_1', 'Semi-Final 1'),
        ('semi_final_2', 'Semi-Final 2'),
        ('final', 'Final'),
    ]
    
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name='votes'
    )
    match_type = models.CharField(max_length=20, choices=MATCH_TYPES)
    voter = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='tournament_votes'
    )
    voted_for = models.ForeignKey(
        EditorApplication,
        on_delete=models.CASCADE,
        related_name='tournament_votes_received',
        help_text="The participant that received this vote"
    )
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [('tournament', 'match_type', 'voter')]
        verbose_name = "Tournament Match Vote"
        verbose_name_plural = "Tournament Match Votes"
        ordering = ['-created_date']
    
    def __str__(self):
        return f"{self.voter.username} voted for {self.voted_for.channel_name} in {self.get_match_type_display()}"


class WeekWinner(models.Model):
    """Model to store Edit of the Week winners separately for tracking and preventing resubmission"""
    
    # Link to the winning EditSubmission
    edit_submission = models.OneToOneField(
        EditSubmission,
        on_delete=models.CASCADE,
        related_name='week_winner_record',
        help_text="The EditSubmission that won"
    )
    
    # Store key information separately for easy querying
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='week_wins',
        help_text="The user who won"
    )
    
    video_url = models.URLField(
        max_length=500,
        help_text="The winning video URL (prevents resubmission)"
    )
    
    week_start = models.DateField(
        help_text="Monday of the competition week"
    )
    
    week_rank = models.IntegerField(
        help_text="Rank in Edit of the Week (1, 2, or 3)"
    )
    
    channel_type = models.CharField(
        max_length=20,
        choices=EditSubmission.CHANNEL_TYPE_CHOICES,
        help_text="Platform type (YouTube or TikTok)"
    )
    
    channel_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Channel name at time of win"
    )
    
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Edit title at time of win"
    )
    
    calculated_points = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Points at time of win"
    )
    
    created_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-week_start', 'week_rank']
        unique_together = ('video_url', 'week_start')  # Same video can't win twice in same week
        indexes = [
            models.Index(fields=['video_url']),  # For quick lookup when checking if video was a winner
            models.Index(fields=['week_start', 'week_rank']),  # For querying winners by week
            models.Index(fields=['user']),  # For querying user's wins
        ]
        verbose_name = "Week Winner"
        verbose_name_plural = "Week Winners"
    
    def __str__(self):
        return f"Week {self.week_start} - Rank #{self.week_rank} - {self.channel_name or self.user.username}"


# Signal to automatically create WeekWinner records when week_rank is set to 1, 2, or 3
@receiver(post_save, sender=EditSubmission)
def create_week_winner_record(sender, instance, created, **kwargs):
    """
    Automatically create a WeekWinner record when an EditSubmission's week_rank
    is set to 1, 2, or 3. This prevents duplicate winner records and ensures
    winner videos cannot be resubmitted.
    """
    # Only create/update winner record if week_rank is 1, 2, or 3
    if instance.week_rank in [1, 2, 3] and instance.scheduled_week:
        try:
            # Check if WeekWinner record already exists for this submission
            winner_record = instance.week_winner_record
            # Update existing record
            winner_record.week_rank = instance.week_rank
            winner_record.week_start = instance.scheduled_week
            winner_record.calculated_points = instance.calculated_points or 0.00
            winner_record.channel_name = instance.channel_name or ''
            winner_record.title = instance.title or ''
            winner_record.save(update_fields=['week_rank', 'week_start', 'calculated_points', 'channel_name', 'title'])
        except WeekWinner.DoesNotExist:
            # Check if this video_url already has a winner record (shouldn't happen, but safety check)
            existing_winner = WeekWinner.objects.filter(video_url=instance.video_url).first()
            if not existing_winner:
                # Create new WeekWinner record
                WeekWinner.objects.create(
                    edit_submission=instance,
                    user=instance.user,
                    video_url=instance.video_url,
                    week_start=instance.scheduled_week,
                    week_rank=instance.week_rank,
                    channel_type=instance.channel_type,
                    channel_name=instance.channel_name or '',
                    title=instance.title or '',
                    calculated_points=instance.calculated_points or 0.00
                )
            else:
                # Update existing winner record (edge case: same video won in different week)
                existing_winner.week_rank = instance.week_rank
                existing_winner.week_start = instance.scheduled_week
                existing_winner.calculated_points = instance.calculated_points or 0.00
                existing_winner.save(update_fields=['week_rank', 'week_start', 'calculated_points'])