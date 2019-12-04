## 背景

PNG 图片相对于 JPEG 图片来说，它是一种无损的图像存储格式，同时多了一条透明度通道，所以一般情况下，PNG 图片要比 JPEG 图片要大，并且 PNG 图片往往还是 APK 图片资源中的大头，所以优化 PNG 图片的大小，对于减小包的体积来说，是比较有回报的事情。

> 关于 PNG 的 wiki：
>
> **便携式网络图形**（英语：**P**ortable **N**etwork **G**raphics，**PNG**）是一种[无损压缩](https://zh.wikipedia.org/wiki/无损压缩)的[位图](https://zh.wikipedia.org/wiki/位图)图形格式，支持索引、[灰度](https://zh.wikipedia.org/wiki/灰度)、[RGB](https://zh.wikipedia.org/wiki/RGB)三种颜色方案以及[Alpha通道](https://zh.wikipedia.org/wiki/Alpha通道)等特性。
>
> 关于 JPEG 的 wiki：
>
> **联合图像专家小组**（英语：**J**oint **P**hotographic **E**xperts **G**roup，缩写：**JPEG**）是一种针对照片影像而广泛使用的[有损压缩](https://zh.wikipedia.org/wiki/有损数据压缩)标准方法。

## 常用的压缩算法

关于 PNG 的压缩算法有很多，这里我们只说两种比较常用的：[Indexed_color](https://en.wikipedia.org/wiki/Indexed_color) 和 [Color_quantization](https://en.wikipedia.org/wiki/Color_quantization)。这两种也是 Google 在 Android 开发者网站上推荐的，具体可以看 [network-xfer](https://developer.android.com/topic/performance/network-xfer)。

下面我们会简单说下这两种算法的大概原理，更深入的知识请移步 Google 或者 Wiki。

### Indexed_color

字面意思就是索引颜色，通过将具体的 ARGB 颜色存储转换成索引下表，来减少文件的大小。我们知道 ARGB 中，每个通道的存储都需要 8 位，也就是 1 字节，一个 ARGB 存储就需要 4 字节，而索引的存储只需要 1 字节。而索引指向的颜色会存放在一个叫 palette（调色板）的数组里面。

> wiki 定义：
>
> 在计算中，**索引颜色**是一种以有限的方式管理[数字图像](https://en.wikipedia.org/wiki/Digital_image)颜色的技术，以节省计算机[内存](https://en.wikipedia.org/wiki/Computer_data_storage)和[文件存储空间](https://en.wikipedia.org/wiki/Hard_disk_drive)，同时加快显示刷新和文件传输的速度。它是[矢量量化压缩的](https://en.wikipedia.org/wiki/Vector_quantization#Use_in_data_compression)一种形式。

图片来自于 wiki：

![Indexed_color](https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/Indexed_palette.svg/150px-Indexed_palette.svg.png)

这种算法很好，但也有缺点，调色板的大小通常只支持 4,16,256 这几种，也就是说最大不会超过 256 个，所以能应用这种算法的 PNG 图片中的颜色使用不能超过 256 个。

### Color_quantization

字面意思就是颜色矢量化，通过使用相似颜色来减少图像中使用的颜色种类，再配合调色板，来达到减少图片文件大小的目的，这是一种有损的压缩算法。

图片来自于 wiki：

这是使用标准的 24 位 RGB 颜色的图像： 

![24位RGB](https://upload.wikimedia.org/wikipedia/commons/e/e3/Dithering_example_undithered.png)

这是优化成只使用 16 种颜色的图像：

![16种颜色](https://upload.wikimedia.org/wikipedia/en/4/48/Dithering_example_undithered_16color_palette.png)

这种算法的缺点就是质量有损，所以如何在质量和大小中间达到一个平衡点，这个至关重要。

## 谈谈 AAPT

AAPT 是 Android 的资源打包工具，我们常用的 R 文件就是用它生存的，除此之外，它还有压缩 PNG 图片的功能。AAPT 现在有 AAPT 和 AAPT2 了，默认我们都是说的是 AAPT2。

> 关于 AAPT2 对于 PNG 图片的压缩知识，可以看下 Colt McAnlis 的这篇文章，[Smaller PNGs, and Android’s AAPT tool](https://medium.com/@duhroach/smaller-pngs-and-android-s-aapt-tool-4ce38a24019d)
>
> PS：作者就是 Android 性能宝典里面那个光头。。。

AAPT2 对于 PNG 图片的压缩可以分为三个方面：

* RGB 是否可以转化成灰度
* 透明通道是否可以删除
* 是不是最多只有 256 色（Indexed_color 优化）

接下来，我们从源码入手，只看看上面所说的这几点吧。

> 源码分析用的是 Android 6.0 也就是 marshmallow 的版本：
>
> https://android.googlesource.com/platform/frameworks/base/+/marshmallow-dev/tools/aapt2/Png.cpp

对于 PNG 的分析代码位于 `analyze_image()` 这个方法中，国际惯例，删除一些不影响分析的代码。

``` cpp
static void analyze_image() {
    int w = imageInfo.width;
    int h = imageInfo.height;
    uint32_t colors[256], col;
    int num_colors = 0;
    bool isOpaque = true;
    bool isPalette = true;
    bool isGrayscale = true;
    // Scan the entire image and determine if:
    // 1. Every pixel has R == G == B (grayscale)
    // 2. Every pixel has A == 255 (opaque)
    // 3. There are no more than 256 distinct RGBA colors
    for (j = 0; j < h; j++) {
        const png_byte* row = imageInfo.rows[j];
        png_bytep out = outRows[j];
        for (i = 0; i < w; i++) {
            rr = *row++;
            gg = *row++;
            bb = *row++;
            aa = *row++;
            int odev = maxGrayDeviation;
            maxGrayDeviation = MAX(ABS(rr - gg), maxGrayDeviation);
            maxGrayDeviation = MAX(ABS(gg - bb), maxGrayDeviation);
            maxGrayDeviation = MAX(ABS(bb - rr), maxGrayDeviation);
          
            // Check if image is really grayscale
            if (isGrayscale) {
                if (rr != gg || rr != bb) {
                  // ==>> Code 1
                    isGrayscale = false;
                }
            }
            // Check if image is really opaque
            if (isOpaque) {
                if (aa != 0xff) {
                  // ==>> Code 2
                    isOpaque = false;
                }
            }
            // Check if image is really <= 256 colors
            if (isPalette) {
                col = (uint32_t) ((rr << 24) | (gg << 16) | (bb << 8) | aa);
                bool match = false;
                for (idx = 0; idx < num_colors; idx++) {
                    if (colors[idx] == col) {
                        match = true;
                        break;
                    }
                }
                if (!match) {
                    if (num_colors == 256) {
                      // ==>> Code 3
                        isPalette = false;
                    } else {
                        colors[num_colors++] = col;
                    }
                }
            }
        }
    }
    *paletteEntries = 0;
    *hasTransparency = !isOpaque;
    int bpp = isOpaque ? 3 : 4;
    int paletteSize = w * h + bpp * num_colors;
    
    // Choose the best color type for the image.
    // 1. Opaque gray - use COLOR_TYPE_GRAY at 1 byte/pixel
    // 2. Gray + alpha - use COLOR_TYPE_PALETTE if the number of distinct combinations
    //     is sufficiently small, otherwise use COLOR_TYPE_GRAY_ALPHA
    // 3. RGB(A) - use COLOR_TYPE_PALETTE if the number of distinct colors is sufficiently
    //     small, otherwise use COLOR_TYPE_RGB{_ALPHA}
    if (isGrayscale) {
        if (isOpaque) {
          // ==>> Code 4
            *colorType = PNG_COLOR_TYPE_GRAY; // 1 byte/pixel
        } else {
            // Use a simple heuristic to determine whether using a palette will
            // save space versus using gray + alpha for each pixel.
            // This doesn't take into account chunk overhead, filtering, LZ
            // compression, etc.
            if (isPalette && (paletteSize < 2 * w * h)) {
              // ==>> Code 5
                *colorType = PNG_COLOR_TYPE_PALETTE; // 1 byte/pixel + 4 bytes/color
            } else {
              // ==>> Code 6
                *colorType = PNG_COLOR_TYPE_GRAY_ALPHA; // 2 bytes per pixel
            }
        }
    } else if (isPalette && (paletteSize < bpp * w * h)) {
      // ==>> Code 7
        *colorType = PNG_COLOR_TYPE_PALETTE;
    } else {
        if (maxGrayDeviation <= grayscaleTolerance) {
          // ==>> Code 8
            *colorType = isOpaque ? PNG_COLOR_TYPE_GRAY : PNG_COLOR_TYPE_GRAY_ALPHA;
        } else {
          // ==>> Code 9
            *colorType = isOpaque ? PNG_COLOR_TYPE_RGB : PNG_COLOR_TYPE_RGB_ALPHA;
        }
    }
    
}
```

首先定义了 3 个变量分别表示：isOpaque（是否不透明），isPalette（是否支持调色板），isGrayscale（是否可转化为灰度）。

首先看 Code 1 处的代码：

``` cpp
                if (rr != gg || rr != bb) {
                  // ==>> Code 1
                    isGrayscale = false;
                }
```

只有 RGB 三种通道的颜色都一样，才能转化成灰度。

Code 2 处的代码是判断透明通道是否为 0，也就是是不是不透明：

``` cpp
                if (aa != 0xff) {
                  // ==>> Code 2
                    isOpaque = false;
                }
```

而 Code 3 处则是判断是否可以用 256 色的调色板：

``` cpp
                if (!match) {
                    if (num_colors == 256) {
                      // ==>> Code 3
                        isPalette = false;
                    } else {
                        colors[num_colors++] = col;
                    }
                }
```

`colors` 是一个数组，里面存放的是图片中已经出现的（不重复）颜色，当颜色的数量大于 256 即表示不支持调色板模式。

然后根据这些条件，来判断使用哪种存储模式，AAPT 中支持的存储模式有以下几种：

* PNG_COLOR_TYPE_PALETTE

  使用调色板模式，最终图片的大小就是 一个像素 1 字节 + 调色板中一个颜色 4 字节

* PNG_COLOR_TYPE_GRAY

  灰度模式，这种是最节省的模式，一个像素 1 字节

* PNG_COLOR_TYPE_GRAY_ALPHA

  灰度模式，同时存在透明通道，一个像素 2 字节

* PNG_COLOR_TYPE_RGB

  RGB 模式，删除了透明通道，一个像素 3 字节

* PNG_COLOR_TYPE_RGB_ALPHA

  ARGB 模式，一个像素 4 字节

### PNG_COLOR_TYPE_PALETTE

要使用这种模式，需要满足以下两个条件，分别是 Code 5 和 Code 7：

Code 5

``` cpp
 if (isGrayscale) {
        if (isOpaque) {
        } else {
          if (isPalette && (paletteSize < 2 * w * h)) {
            // ==>> Code 5
                *colorType = PNG_COLOR_TYPE_PALETTE; // 1 byte/pixel + 4 bytes/color
            } 
        }
 }
```

在支持灰度模式的前提下，有透明通道，支持调色板模式，同时调色板的长度小于 `2 * w * h`。

Code 7

``` cpp
if (isGrayscale) {
  
} else {
  if (isPalette && (paletteSize < bpp * w * h)) {
    // Code ==>> 7
        *colorType = PNG_COLOR_TYPE_PALETTE;
    }
}
```

如果不支持灰度模式，但支持调色板，同时调色板长度小于 `bpp * w * h`，其中 `bpp` 的大小根据是否为不透明为决定：

``` cpp
    int bpp = isOpaque ? 3 : 4;
```

### PNG_COLOR_TYPE_GRAY

要使用这种模式，需要满足支持灰度模式，同时不透明。代码位于 Code 4：

``` cpp
 if (isGrayscale) {
        if (isOpaque) {
          // ==>> Code 4
            *colorType = PNG_COLOR_TYPE_GRAY; // 1 byte/pixel
        }
 }
```

###PNG_COLOR_TYPE_GRAY_ALPHA

灰度，同时存在透明通道的模式。代码位于 Code 6 和 Code 8：

Code 6

``` cpp
 if (isGrayscale) {
        if (isOpaque) {
        } else {
          if (isPalette && (paletteSize < 2 * w * h)) {
            } else {
            // ==>> Code 6
            *colorType = PNG_COLOR_TYPE_GRAY_ALPHA; // 2 bytes per pixel
          }
        }
 }
```

Code 8

``` cpp
if (isGrayscale) {
        
    } else if (isPalette && (paletteSize < bpp * w * h)) {
    } else {
        if (maxGrayDeviation <= grayscaleTolerance) {
          // ==>> Code 8
            *colorType = isOpaque ? PNG_COLOR_TYPE_GRAY : PNG_COLOR_TYPE_GRAY_ALPHA;
        } else {
        }
    }

```

`maxGrayDeviation` 是计算 RGB 通道直接的差值，如果小于 `grayscaleTolerance` 这个阙值，那么也可以转成灰度。

### PNG_COLOR_TYPE_RGB

不透明图片可以删除透明通道，代码位于 Code 9：

``` cpp
if (isGrayscale) {
        
    } else if (isPalette && (paletteSize < bpp * w * h)) {
    } else {
        if (maxGrayDeviation <= grayscaleTolerance) {
        } else {
          // ==>> Code 9
                      *colorType = isOpaque ? PNG_COLOR_TYPE_RGB : PNG_COLOR_TYPE_RGB_ALPHA;
        }
    }


```

### PNG_COLOR_TYPE_RGB_ALPHA

这个没什么好说的，最后的兜底模式。

### 小结

AAPT 对 PNG 的优化，主要是 Indexed_color 算法，这也是一种保守的选择，因为这种是无损的，如果我们想要更高的压缩率，可以使用一些其他的压缩工具，来集成到我们的编译打包流程中。

## PNG 压缩工具对比

首先，在我们选择其他 PNG 压缩工具其他，我们需要先禁用 AAPT 的默认压缩模式，因为对于 PNG 的压缩，并不是 1 + 1 > 2，可以通过以下代码关闭：

``` groovy
android {
     aaptOptions {
        cruncherEnabled = false
    }
}
```

现在常用的 PNG 压缩工具有 [pngcrush](http://pmt.sourceforge.net/pngcrush/)、[pngquant](https://pngquant.org/)、[zopfli](https://github.com/google/zopfli) 、[tinypng](https://tinypng.com) 等，这里我们就先不考虑 tinypng，因为这个只提供了 HTTP 接口的形式，并且有次数限制。

### 使用 Gradle 集成

为了将 PNG 压缩工具集成到 APK 的构建编译流程，我们使用 Gradle 来实现。作者当前使用 Android Gradle 插件版本为 3.5.0，在这个版本我们可以通过 `ApplicationVariant.allRawAndroidResources` 获取所有的资源目录。

需要注意的是，我们这个 Task 需要在 MergeResources 这个 Task 之前执行，这样我们可以将压缩后的同名覆盖，再合并到 APK 文件中。

``` groovy
afterEvaluate {

        applicationVariants.all { ApplicationVariant variant ->

            if (variant.buildType.name != "release") {
                return
            }


            def compressPngTask = task('compressPng')
            compressPngTask.doLast {
                List<File> allResource = []

                variant.allRawAndroidResources.files.forEach { dir ->

                    if (!dir.exists()) {
                        return
                    }

                    if (dir.isFile()) {
                        if (dir.name.endsWith(".png")) {
                            allResource.add(file)
                        }
                    } else {
                        dir.traverse { file ->
                            if (file.name.endsWith(".png")) {
                                allResource.add(file)
                            }
                        }
                    }


                }


                allResource.forEach { file ->
                    // kb
                    def oldSize = file.size() / 1024f

                    println "path = ${file.path}"
                    try {
                       // TODO 这里就是我们执行压缩的逻辑
                    } catch (Throwable ignore) {
                        println "file: ${file.name} error: ${ignore.message}"
                    }


                    println "${file.name}: $oldSize KB ==> ${file.size() / 1024f} KB"

                }


            }


            Task mergeResourcesTask = variant.mergeResourcesProvider.get()
            mergeResourcesTask.dependsOn(compressPngTask)
        }


    }
```

首先我们创建一个名为 compressPng 的 Task，这个 Task 的任务就是收集所有 PNG 文件路径，这里我们过滤掉 BuildType 不是 release 的 Variant，最后让 MergeResources Task 依赖于 compressPng Task。

**记得先关掉 AAPT 默认的 PNG 压缩。**

这里我们先记录下关闭 AAPT 默认 PNG 压缩后的 APK 文件大小，和使用默认 PNG 压缩后的 APK 文件大小：

> 这里我找的是一个直播的项目，里面有比较多的图片资源文件，过滤了 JPEG 和 .9 图，大概有 1000多张 PNG 图片，只使用一个压缩线程。

| 压缩工具 | APK 大小（MB） | 耗时   |
| -------- | -------------- | ------ |
| 无       | 81.9           | 29s    |
| AAPT     | 78.9           | 1m 18s |

### pngquant

首先测试 pngquant，我们将pngquant 集成进去：

``` groovy
                        exec { ExecSpec spec ->
                            spec.workingDir(project.file('.'))
                            spec.commandLine("./pngquant", "--skip-if-larger", "--speed", "1", "--strip", "--nofs", "--force", "--output", file.path, "--", file.path)
                        }
```

这里我们用的基本都是默认配置：

* --skip-if-larger 表示如果压缩后的图片更大了，就跳过
* --speed 1 表示使用最慢的压缩速度，来换取更好的压缩质量
* --strip 删除图片的一些元数据
* --nofs 禁用 [Floyd–Steinberg dithering]([https://en.wikipedia.org/wiki/Floyd%E2%80%93Steinberg_dithering](https://en.wikipedia.org/wiki/Floyd–Steinberg_dithering)) 图像抖动处理
* --force 覆盖源文件
* --output 输出文件的路径

先执行 Clean Task，再重新执行打包，最终结果如下：

| 压缩工具 | APK 大小（MB） | 耗时   |
| -------- | -------------- | ------ |
| 无       | 81.9           | 29s    |
| AAPT     | 78.9           | 32s    |
| pngquant | 73.7           | 1m 18s |

### zopflipng

集成进去：

``` groovy
                        exec { ExecSpec spec ->
                            spec.workingDir(new File('/Users/leo/Documents/projects/zopfli'))
                            spec.commandLine("./zopflipng", "-y", "-m", file.path, file.path)

                        }
```

使用的也是基本配置：

* -y 覆盖原文件，不需要询问
* -m 尽可能多压缩，依赖于文件的大小

先执行 Clean Task，再重新执行打包，最终结果如下：

| 压缩工具  | APK 大小（MB） | 耗时    |
| --------- | -------------- | ------- |
| 无        | 81.9           | 29s     |
| AAPT      | 78.9           | 32s     |
| pngquant  | 73.7           | 1m 18s  |
| zopflipng | 78             | 36m 17s |

### pngcursh

集成进去：

``` groovy
                        exec { ExecSpec spec ->
                            spec.workingDir(new File('/Users/leo/Documents/projects/pngcrush-1.8.13'))
                            spec.commandLine("./pngcrush", "-ow","-reduce", file.path)
                        }
```

使用基本配置：

* -ow 表示覆盖原文件
* -reduce 减少无损颜色值的类型和位深度
* -brute 尝试 176 种压缩方法

先执行 Clean Task，再重新执行打包，最终结果如下：

| 压缩工具  | APK 大小（MB） | 耗时    |
| --------- | -------------- | ------- |
| 无        | 81.9           | 29s     |
| AAPT      | 78.9           | 32s     |
| pngquant  | 73.7           | 1m 18s  |
| zopflipng | 78             | 36m 17s |
| pngcursh  | 78.7           | 13m 56s |

### 小结

虽然从结果上来看，pngquant 是最好的选择，但因为 pngcursh 这块使用的只是默认的压缩配置，而且 pngcursh 提供的参数是最多的，所以具体哪个更优，只能靠调参数了，众所周知，调参数也是技术活。

## 总结

推荐使用 WebP 和 SVG 来代替 PNG 和 JPEG 图片的使用，但有些三方库的图片是我们没办法控制的，这块就可以用 PNG 压缩工具来进行优化。至于如果平衡压缩率、压缩耗时，这就是要靠大家去调参数了。