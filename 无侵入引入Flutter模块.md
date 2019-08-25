### 前言
Flutter 作为当下比较流行的技术，不少公司已经开始在原生项目中接入它，但这也带来了一些问题：

  * Flutter SDK 问题，在 Android 中，Flutter 的代码和 Framework 会被编译成产物，而且 debug 和 release 生成的产物也是不太一样的。要编译就需要有 SDK，这意味着其他成员也需要下载 Flutter SDK，即使他不需要开发 Flutter 模块，还有 Flutter 版本的管理也是一个问题，不过这个已经有解决方案了。
  * Android 和 iOS 项目需要共用一套 Flutter 代码，这就需要用合适的方式去管理 Flutter 模块。

> 文章基于 v1.5.4-hotfix.2 Flutter SDK 版本

### Flutter的接入

要优化它，就需要先了解它。以 Android 为例，要接入 Flutter 很方便，首先在 settings.gradle 中：

``` groovy
def flutterProjectRoot = rootProject.projectDir.parentFile.toPath()

def plugins = new Properties()
def pluginsFile = new File(flutterProjectRoot.toFile(), '.flutter-plugins')
if (pluginsFile.exists()) {
    pluginsFile.withReader('UTF-8') { reader -> plugins.load(reader) }
}

plugins.each { name, path ->
    def pluginDirectory = flutterProjectRoot.resolve(path).resolve('android').toFile()
    include ":$name"
    project(":$name").projectDir = pluginDirectory
}
```

这里会将 Flutter 所依赖的第三方插件，include 到我们项目中，而相关的配置就记录在 .flutter-plugins 中。接着在 app 模块下的 build.gradle 中：

``` groovy
apply from: "$flutterRoot/packages/flutter_tools/gradle/flutter.gradle"
```

flutter.gradle 这个文件在 Flutter SDK 目录中，我们上面说到编译成产物的操作就是在这个脚本中定义的。所以我们注重看下这个文件：

``` groovy
apply plugin: FlutterPlugin
```

FlutterPlugin 是一个自定义的 Gradle Plugin，而且也是定义在这个文件中的。

``` groovy
project.android.buildTypes {                            
    profile {                                           
        initWith debug                                  
        if (it.hasProperty('matchingFallbacks')) {      
            matchingFallbacks = ['debug', 'release']    
        }                                               
    }                                                   
    dynamicProfile {                                    
        initWith debug                                  
        if (it.hasProperty('matchingFallbacks')) {      
            matchingFallbacks = ['debug', 'release']    
        }                                               
    }                                                   
    dynamicRelease {                                    
        initWith debug                                  
        if (it.hasProperty('matchingFallbacks')) {      
            matchingFallbacks = ['debug', 'release']    
        }                                               
    }                                                   
}                                                       
```

除了默认的 debug 和 release 之外，Flutter 会定义 profile、dynamicProfile、dynamicRelease 这三种 buildType，这里需要注意下，如果项目已经定义了同名的 buildType 的话。`matchingFallbacks` 表示如果引用的模块中不存在相同的 buildType，则使用这些替补选项。

``` groovy
if (project.hasProperty('localEngineOut')) {
 //...
}
```

`localEngineOut` 可以用于指定特定的 engine 目录，默认用 SDK 中的，如果自己重新编译了 engine，可以用这个选项来指向。具体可见：[Flutter-Engine-编译指北]([https://fucknmb.com/2019/02/26/Flutter-Engine-%E7%BC%96%E8%AF%91%E6%8C%87%E5%8C%97/](https://fucknmb.com/2019/02/26/Flutter-Engine-编译指北/))

``` groovy
Path baseEnginePath = Paths.get(flutterRoot.absolutePath, "bin", "cache", "artifacts", "engine")                              
String targetArch = 'arm'                                                                                                     
if (project.hasProperty('target-platform') &&                                                                                 
    project.property('target-platform') == 'android-arm64') {                                                                 
  targetArch = 'arm64'                                                                                                        
}                                                                                                                             
debugFlutterJar = baseEnginePath.resolve("android-${targetArch}").resolve("flutter.jar").toFile()                             
profileFlutterJar = baseEnginePath.resolve("android-${targetArch}-profile").resolve("flutter.jar").toFile()                   
releaseFlutterJar = baseEnginePath.resolve("android-${targetArch}-release").resolve("flutter.jar").toFile()                   
dynamicProfileFlutterJar = baseEnginePath.resolve("android-${targetArch}-dynamic-profile").resolve("flutter.jar").toFile()    
dynamicReleaseFlutterJar = baseEnginePath.resolve("android-${targetArch}-dynamic-release").resolve("flutter.jar").toFile()    
if (!debugFlutterJar.isFile()) {                                                                                              
    project.exec {                                                                                                            
        executable flutterExecutable.absolutePath                                                                             
        args "--suppress-analytics"                                                                                           
        args "precache"                                                                                                       
    }                                                                                                                         
    if (!debugFlutterJar.isFile()) {                                                                                          
        throw new GradleException("Unable to find flutter.jar in SDK: ${debugFlutterJar}")                                    
    }                                                                                                                         
}                                                                                                                             
                                                                                                                              
// Add x86/x86_64 native library. Debug mode only, for now.                                                                   
flutterX86Jar = project.file("${project.buildDir}/${AndroidProject.FD_INTERMEDIATES}/flutter/flutter-x86.jar")                
Task flutterX86JarTask = project.tasks.create("${flutterBuildPrefix}X86Jar", Jar) {                                           
    destinationDir flutterX86Jar.parentFile                                                                                   
    archiveName flutterX86Jar.name                                                                                            
    from("${flutterRoot}/bin/cache/artifacts/engine/android-x86/libflutter.so") {                                             
        into "lib/x86"                                                                                                        
    }                                                                                                                         
    from("${flutterRoot}/bin/cache/artifacts/engine/android-x64/libflutter.so") {                                             
        into "lib/x86_64"                                                                                                     
    }                                                                                                                         
}                                                                                                                             
// Add flutter.jar dependencies to all <buildType>Api configurations, including custom ones                                   
// added after applying the Flutter plugin.                                                                                   
project.android.buildTypes.each { addFlutterJarApiDependency(project, it, flutterX86JarTask) }                                
project.android.buildTypes.whenObjectAdded { addFlutterJarApiDependency(project, it, flutterX86JarTask) }                     
```

这里的代码看起来很长，其实做的事情就是一件，添加 flutter.jar 依赖，不同的 buildType 添加不同的版本，debug 模式额外增加 x86/x86_64 架构的版本。

``` groovy
project.extensions.create("flutter", FlutterExtension)   
project.afterEvaluate this.&addFlutterTask               
```

首先添加一个 FlutterExtension 配置块，可选的配置有 source 和 target，用于指定编写的 Flutter 代码目录和执行 Flutter 代码的入口 dart 文件，默认为 `lib/main.dart`。

在 `afterEvaluate` 钩子上添加一个执行方法：addFlutterTask。

`verbose`、`filesystem-roots`、`filesystem-scheme` 这些一些额外可选的参数，这里我们先不关心。

``` groovy
if (project.android.hasProperty("applicationVariants")) {   
    project.android.applicationVariants.all addFlutterDeps  
} else {                                                    
    project.android.libraryVariants.all addFlutterDeps      
}                                                           
```

存在 `applicationVariants` 属性表示当前接入 Flutter 的模块是使用 `com.android.application`，`applicationVariants` 和 `libraryVariants` 都是表示当前模块的构建变体，`addFlutterDeps` 是一个闭包，这里的意思是，遍历所有变体，调用 addFlutterDeps。

``` groovy
def addFlutterDeps = { variant ->                                                                                                        
    String flutterBuildMode = buildModeFor(variant.buildType)                                                                            
    if (flutterBuildMode == 'debug' && project.tasks.findByName('${flutterBuildPrefix}X86Jar')) {                                        
        Task task = project.tasks.findByName("compile${variant.name.capitalize()}JavaWithJavac")                                         
        if (task) {                                                                                                                      
            task.dependsOn project.flutterBuildX86Jar                                                                                    
        }                                                                                                                                
        task = project.tasks.findByName("compile${variant.name.capitalize()}Kotlin")                                                     
        if (task) {                                                                                                                      
            task.dependsOn project.flutterBuildX86Jar                                                                                    
        }                                                                                                                                
    }                                                                                                                                    
                                                                                                                                         
    FlutterTask flutterTask = project.tasks.create(name: "${flutterBuildPrefix}${variant.name.capitalize()}", type: FlutterTask) {       
        flutterRoot this.flutterRoot                                                                                                     
        flutterExecutable this.flutterExecutable                                                                                         
        buildMode flutterBuildMode                                                                                                       
        localEngine this.localEngine                                                                                                     
        localEngineSrcPath this.localEngineSrcPath                                                                                       
        targetPath target                                                                                                                
        verbose verboseValue                                                                                                             
        fileSystemRoots fileSystemRootsValue                                                                                             
        fileSystemScheme fileSystemSchemeValue                                                                                           
        trackWidgetCreation trackWidgetCreationValue                                                                                     
        compilationTraceFilePath compilationTraceFilePathValue                                                                           
        createPatch createPatchValue                                                                                                     
        buildNumber buildNumberValue                                                                                                     
        baselineDir baselineDirValue                                                                                                     
        buildSharedLibrary buildSharedLibraryValue                                                                                       
        targetPlatform targetPlatformValue                                                                                               
        sourceDir project.file(project.flutter.source)                                                                                   
        intermediateDir project.file("${project.buildDir}/${AndroidProject.FD_INTERMEDIATES}/flutter/${variant.name}")                   
        extraFrontEndOptions extraFrontEndOptionsValue                                                                                   
        extraGenSnapshotOptions extraGenSnapshotOptionsValue                                                                             
    }                                                                                                                                    
                                                                                                                                         
    // We know that the flutter app is a subproject in another Android app when these tasks exist.                                       
    Task packageAssets = project.tasks.findByPath(":flutter:package${variant.name.capitalize()}Assets")                                  
    Task cleanPackageAssets = project.tasks.findByPath(":flutter:cleanPackage${variant.name.capitalize()}Assets")                        
                                                                                                                                         
    Task copyFlutterAssetsTask = project.tasks.create(name: "copyFlutterAssets${variant.name.capitalize()}", type: Copy) {               
        dependsOn flutterTask                                                                                                            
        if (packageAssets && cleanPackageAssets) {                                                                                       
            dependsOn packageAssets                                                                                                      
            dependsOn cleanPackageAssets                                                                                                 
            into packageAssets.outputDir                                                                                                 
        } else {                                                                                                                         
            dependsOn variant.mergeAssets                                                                                                
            dependsOn "clean${variant.mergeAssets.name.capitalize()}"                                                                    
            into variant.mergeAssets.outputDir                                                                                           
        }                                                                                                                                
        with flutterTask.assets                                                                                                          
    }                                                                                                                                    
                                                                                                                                         
    if (packageAssets) {                                                                                                                 
        String mainModuleName = "app"                                                                                                    
        try {                                                                                                                            
            String tmpModuleName = project.rootProject.ext.mainModuleName                                                                
            if (tmpModuleName != null && !tmpModuleName.empty) {                                                                         
                mainModuleName = tmpModuleName                                                                                           
            }                                                                                                                            
        } catch (Exception e) {                                                                                                          
        }                                                                                                                                
        // Only include configurations that exist in parent project.                                                                     
        Task mergeAssets = project.tasks.findByPath(":${mainModuleName}:merge${variant.name.capitalize()}Assets")                        
        if (mergeAssets) {                                                                                                               
            mergeAssets.dependsOn(copyFlutterAssetsTask)                                                                                 
        }                                                                                                                                
    } else {                                                                                                                             
        variant.outputs[0].processResources.dependsOn(copyFlutterAssetsTask)                                                             
    }                                                                                                                                    
}                                                                                                                                        
```

`variant` 就是上面遍历的构建变体。首先当构建类型为 debug 时，会在 compileJavaWithJavac 和 compileKotlin 这两个 task 之前先执行 flutterBuildX86Jar task。它的作用是引入 x86 架构的 jar 和 so 文件。

> 这里有个 bug
>
> ``` groovy
> project.tasks.findByName('${flutterBuildPrefix}X86Jar')
> ```
>
> 判断是否存在 task 时，拼接字符串用的是单引号，正确应该用双引号，最新版本已经改正了。

接下来，会创建两个 task，flutterBuild 和 copyFlutterAssets，flutterBuild 用于编译产物，copyFlutterAssets 则是将产物拷贝到 assets 目录。因为使用 `com.android.application` 和 `com.android.library` 拥有的 task 是不一样的，所有这里用是否存在 packageAssets 和 cleanPackageAssets 这两个 task 去判断引用不同插件的模块，同时引入 library 插件的模块，flutterBuild 需要依赖于这两个 task。

flutterBuild task 实际上 FlutterTask 类型，同时 FlutterTask 继承于 BaseFlutterTask。

``` groovy
abstract class BaseFlutterTask extends DefaultTask { 
@OutputFiles                                                                
FileCollection getDependenciesFiles() {                                     
    FileCollection depfiles = project.files()                               
                                                                            
    // Include the kernel compiler depfile, since kernel compile is the     
    // first stage of AOT build in this mode, and it includes all the Dart  
    // sources.                                                             
    depfiles += project.files("${intermediateDir}/kernel_compile.d")        
                                                                            
    // Include Core JIT kernel compiler depfile, since kernel compile is    
    // the first stage of JIT builds in this mode, and it includes all the  
    // Dart sources.                                                        
    depfiles += project.files("${intermediateDir}/snapshot_blob.bin.d")     
    return depfiles                                                         
}                                                                           
}
```

`@OutputFiles` 注解用于标示 task 输出的目录，这个可以用来做增量编译和任务缓存等等。

``` groovy
class FlutterTask extends BaseFlutterTask {
  @TaskAction      
void build() {   
    buildBundle()
}                
}

void buildBundle() {                                                                         
    if (!sourceDir.isDirectory()) {                                                          
        throw new GradleException("Invalid Flutter source directory: ${sourceDir}")          
    }                                                                                        
                                                                                             
    intermediateDir.mkdirs()                                                                 
                                                                                             
    if (buildMode == "profile" || buildMode == "release") {                                  
        project.exec {                                                                       
            executable flutterExecutable.absolutePath                                        
            workingDir sourceDir                                                             
            if (localEngine != null) {                                                       
                args "--local-engine", localEngine                                           
                args "--local-engine-src-path", localEngineSrcPath                           
            }                                                                                
            args "build", "aot"                                                              
            args "--suppress-analytics"                                                      
            args "--quiet"                                                                   
            args "--target", targetPath                                                      
            args "--target-platform", "android-arm"                                          
            args "--output-dir", "${intermediateDir}"                                        
            if (trackWidgetCreation) {                                                       
                args "--track-widget-creation"                                               
            }                                                                                
            if (extraFrontEndOptions != null) {                                              
                args "--extra-front-end-options", "${extraFrontEndOptions}"                  
            }                                                                                
            if (extraGenSnapshotOptions != null) {                                           
                args "--extra-gen-snapshot-options", "${extraGenSnapshotOptions}"            
            }                                                                                
            if (buildSharedLibrary) {                                                        
                args "--build-shared-library"                                                
            }                                                                                
            if (targetPlatform != null) {                                                    
                args "--target-platform", "${targetPlatform}"                                
            }                                                                                
            args "--${buildMode}"                                                            
        }                                                                                    
    }                                                                                        
                                                                                             
    project.exec {                                                                           
        executable flutterExecutable.absolutePath                                            
        workingDir sourceDir                                                                 
        if (localEngine != null) {                                                           
            args "--local-engine", localEngine                                               
            args "--local-engine-src-path", localEngineSrcPath                               
        }                                                                                    
        args "build", "bundle"                                                               
        args "--suppress-analytics"                                                          
        args "--target", targetPath                                                          
        if (verbose) {                                                                       
            args "--verbose"                                                                 
        }                                                                                    
        if (fileSystemRoots != null) {                                                       
            for (root in fileSystemRoots) {                                                  
                args "--filesystem-root", root                                               
            }                                                                                
        }                                                                                    
        if (fileSystemScheme != null) {                                                      
            args "--filesystem-scheme", fileSystemScheme                                     
        }                                                                                    
        if (trackWidgetCreation) {                                                           
            args "--track-widget-creation"                                                   
        }                                                                                    
        if (compilationTraceFilePath != null) {                                              
            args "--compilation-trace-file", compilationTraceFilePath                        
        }                                                                                    
        if (createPatch) {                                                                   
            args "--patch"                                                                   
            args "--build-number", project.android.defaultConfig.versionCode                 
            if (buildNumber != null) {                                                       
                assert buildNumber == project.android.defaultConfig.versionCode              
            }                                                                                
        }                                                                                    
        if (baselineDir != null) {                                                           
            args "--baseline-dir", baselineDir                                               
        }                                                                                    
        if (extraFrontEndOptions != null) {                                                  
            args "--extra-front-end-options", "${extraFrontEndOptions}"                      
        }                                                                                    
        if (extraGenSnapshotOptions != null) {                                               
            args "--extra-gen-snapshot-options", "${extraGenSnapshotOptions}"                
        }                                                                                    
        if (targetPlatform != null) {                                                        
            args "--target-platform", "${targetPlatform}"                                    
        }                                                                                    
        if (buildMode == "release" || buildMode == "profile") {                              
            args "--precompiled"                                                             
        } else {                                                                             
            args "--depfile", "${intermediateDir}/snapshot_blob.bin.d"                       
        }                                                                                    
        args "--asset-dir", "${intermediateDir}/flutter_assets"                              
        if (buildMode == "debug") {                                                          
            args "--debug"                                                                   
        }                                                                                    
        if (buildMode == "profile" || buildMode == "dynamicProfile") {                       
            args "--profile"                                                                 
        }                                                                                    
        if (buildMode == "release" || buildMode == "dynamicRelease") {                       
            args "--release"                                                                 
        }                                                                                    
        if (buildMode == "dynamicProfile" || buildMode == "dynamicRelease") {                
            args "--dynamic"                                                                 
        }                                                                                    
    }                                                                                        
}                                                                                            
```

用 `@TaskAction` 表示的方法就是 task 执行时候的方法。这里代码也很长，其实就是执行了两个命令。第一，如果是 release 或 profile 模式下，执行 `flutter build aot`。然后执行 `flutter build bundle`。

### 实现

分析完 Flutter 接入的流程后，再回头去看我们一开始面临的问题，现在我们来解决它。

#### 生成 aar

为了其他成员不需要依赖于 Flutter 环境，首先我们需要将 Flutter 代码提前生成为 aar，之所以不是 jar，是因为有图片资源等。生成产物的命令可以参照 FlutterBuildTask，要注意的是，debug 和 release 模式下生成的产物是不一致的。

debug 模式下的构建产物：

![debug](https://user-gold-cdn.xitu.io/2019/8/22/16cb84ca450f272b?w=460&h=380&f=png&s=39969)

release 模式下的构建产物：

![release](https://user-gold-cdn.xitu.io/2019/8/22/16cb84c97b7471b6?w=474&h=210&f=png&s=24868)

Flutter 产物生成不麻烦，照搬命令即可，这主要解决的问题是，Flutter 模块中依赖的第三方插件，上面我们说到，Flutter 模块依赖的第三方插件会生成到配置文件 .flutter-plugins 中。然后在 settings.gradle 中，将这些项目的源码加入我们项目的依赖中去。所有，我们要提前构建的话，就需要将这些代码也打进我们的 aar 中。可惜，官方不支持这种操作，这时候需要第三方库来支持了，[fataar-gradle-plugin](https://github.com/Mobbeel/fataar-gradle-plugin)，不过这个库有个小坑，Android Gradle 插件 3.1.x 的时候，没有将 jni 目录的 so 输出到 aar 中，解决方式，添加：

``` groovy
project.copy {
                from "${project.projectDir.path}/build/intermediates/library_and_local_jars_jni/${variantName}"
                include "**"
                into "${temporaryDir.path}/${variantName}/jni"
            }
```

经过这两个步骤后，我们就能提前将 Flutter 产物和第三方插件的 aar 都打包一个 aar，上传 maven 上等等。

#### 源码管理

因为 Android 项目和 iOS 项目都需要用到同一套 Flutter 源码，所以这里我们可以使用 git 提供的 submodule 的形式接入源码。关于 Flutter SDK 版本管理，可以参照之前的文章：[flutterw](https://juejin.im/post/5d0c39326fb9a07ef63fe4b0)

### 结尾

因为篇幅原因，所以不能将实现细节完整写出来，只能将一些关键点整理出来，希望能对大家有点启发。有其他疑问，欢迎留言讨论。

