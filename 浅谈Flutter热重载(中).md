## 更新日志

* 本文写于 2019.09.12，Flutter SDK 版本为 v1.5.4-hotfix.2

## 前言

在 [浅谈Flutter热重载(上)](https://juejin.im/post/5d765c9e5188254917372801) 中，我们从热重载整个链路讲起，建立 sockest 连接，同步文件到设备，最后通知 Flutter Engine 刷新视图，其中生成增量包(差异包)这一块我们只是一笔带过，没有细讲，这一块对我们做动态更新是非常重要的一步，所以了解如何生成增量包是这篇文章的目的。

## 生成增量包

当我们使用 `flutter run` 启动应用后，修改代码后再键入 `r` 时，会调用 `ResidentCompiler.recompile()` 重新编译生成增量包：

``` dart
final CompilerOutput compilerOutput = await generator.recompile(                                                
  mainPath,                                                                                                     
  invalidatedFiles,                                                                                             
  outputPath:  dillOutputPath ?? getDefaultApplicationKernelPath(trackWidgetCreation: trackWidgetCreation),     
  packagesFilePath : _packagesFilePath,                                                                         
);                                                                                                              
if (compilerOutput == null) {                                                                                   
  return UpdateFSReport(success: false);                                                                        
}                                                                                                               
```

### 检索修改的文件

注意到这里有个 `invalidatedFiles` 字段，这个是表示无效的 dart 文件，即已经被修改的 dart 文件。关于如何检索已修改的文件，这里用的是 stat 这个命令，通过比较文件的修改时间来判断是否需要更新：

``` dart
static List<Uri> findInvalidated({                                                          
  @required DateTime lastCompiled,                                                          
  @required List<Uri> urisToMonitor,                                                        
  @required String packagesPath,                                                            
}) {                                                                                        
  final List<Uri> invalidatedFiles = <Uri>[];                                               
  int scanned = 0;                                                                          
  final Stopwatch stopwatch = Stopwatch()..start();                                         
  for (Uri uri in urisToMonitor) {                                                          
    if ((platform.isWindows && uri.path.contains(_pubCachePathWindows))                     
        || uri.path.contains(_pubCachePathLinuxAndMac)) {                                   
      // Don't watch pub cache directories to speed things up a little.                     
      continue;                                                                             
    }                                                                                       
    final DateTime updatedAt = fs.statSync(                                                 
        uri.toFilePath(windows: platform.isWindows)).modified;                              
    scanned++;                                                                              
    if (updatedAt == null) {                                                                
      continue;                                                                             
    }                                                                                   
    // 当前修改时间大于最后一次编译的时间
    if (updatedAt.millisecondsSinceEpoch > lastCompiled.millisecondsSinceEpoch) {           
      invalidatedFiles.add(uri);                                                            
    }                                                                                       
  }                                                                                         
  // we need to check the .packages file too since it is not used in compilation.           
  final DateTime packagesUpdatedAt = fs.statSync(packagesPath).modified;                    
  if (lastCompiled != null && packagesUpdatedAt != null                                     
      && packagesUpdatedAt.millisecondsSinceEpoch > lastCompiled.millisecondsSinceEpoch) {  
    invalidatedFiles.add(fs.file(packagesPath).uri);                                        
    scanned++;                                                                              
  }                                                                                         
  printTrace('Scanned through $scanned files in ${stopwatch.elapsedMilliseconds}ms');       
  return invalidatedFiles;                                                                  
}                                                                                           
```

urisToMonitor 表示跟踪的 dart 源文件，这里除了项目本身的，还包括了依赖库的。除了检查 dart 源文件以外，还额外检查了 .packages 文件，这个文件中保存了依赖库的源码目录：

![.packages](https://user-gold-cdn.xitu.io/2019/9/12/16d246605fd7095f?w=850&h=388&f=png&s=172467)

### 重新编译

不管是生成增量包，还是全编译，最后都是调用的 `ResidentCompiler.recompile()` 这个方法。ResidentCompiler 将构建请求抽象成 _CompilationRequest，存放成一个队列去执行：

``` dart
Future<void> _handleCompilationRequest(_CompilationRequest request) async {   
  final bool isEmpty = _compilationQueue.isEmpty;                             
  _compilationQueue.add(request);                                             
  // Only trigger processing if queue was empty - i.e. no other requests      
  // are currently being processed. This effectively enforces "one            
  // compilation request at a time".                                          
  if (isEmpty) {                                                              
    while (_compilationQueue.isNotEmpty) {                                    
      final _CompilationRequest request = _compilationQueue.first;            
      await request.run(this);                                                
      _compilationQueue.removeAt(0);                                          
    }                                                                         
  }                                                                           
}                                                                             
```

最后会调用到 `ResidentCompiler._recompile()` 方法，这里注意和 `ResidentCompiler.recompile()` 的区别，一个是私有方法，一个是公开方法。在 `_recompile()` 的方法体中，如果 `_server` 不等于 null，则调用 `_server.stdin` 写入内容即可，否则就调用 `_compile()` 方法。

``` dart
final String inputKey = Uuid().generateV4();                                
final String mainUri = request.mainPath != null                             
    ? _mapFilename(request.mainPath, packageUriMapper) + ' '                
    : '';                                                                   
_server.stdin.writeln('recompile $mainUri$inputKey');                       
printTrace('<- recompile $mainUri$inputKey');                               
for (Uri fileUri in request.invalidatedFiles) {                             
  _server.stdin.writeln(_mapFileUri(fileUri.toString(), packageUriMapper)); 
  printTrace('<- ${_mapFileUri(fileUri.toString(), packageUriMapper)}');    
}                                                                           
_server.stdin.writeln(inputKey);                                            
printTrace('<- $inputKey');                                                 
```

在 `_compile()` 函数中，会执行 **frontend_server.dart.snapshot** 这个 Dart Snapshot 脚本文件，完整的命令可以简化如下：

``` shell
dart frontend_server.dart.snapshot --sdk-root flutter_patched_sdk --incremental --strong --target=flutter --output-dill build/app.dill --packages .packages --filesystem-scheme org-dartlang-root
```

`--incremental` 表示这次编译为增量编译。

当第一次调用 `_recompile()` 方法时，会调用 `_compile()` 方法去执行 frontend_server.dart.snapshot，这里我们用的是交互模式，后续我们要生成增量包，只需要往输入流中写入命令即可。

编译成功的输出监听同样是在 `_compile()` 函数中注册的：

``` dart
_server.stdout                                                              
  .transform<String>(utf8.decoder)                                          
  .transform<String>(const LineSplitter())                                  
  .listen(                                                                  
    _stdoutHandler.handler,                                                 
    onDone: () {                                                            
      // when outputFilename future is not completed, but stdout is closed  
      // process has died unexpectedly.                                     
      if (!_stdoutHandler.compilerOutput.isCompleted) {                     
        _stdoutHandler.compilerOutput.complete(null);                       
      }                                                                     
    });                                                                     
```

在 `handler()` 函数中，编译成功情况下，正常的输出应该是这样的：

1. "result <boundaryKey>"

   从这里获取 boundaryKey 用来给后面接收的消息进行分割

2. <compiler output>

   这里会输出 boundaryKey

3. "<boundaryKey> [<dill-file>] errorCount"

   根据第一步获取的 boundaryKey 来匹配获取生成的 dill 文件，这里可以是完整的 dill 文件，也可以是增量生成的。

### Frontend Server

> Front end 是编译的第一个阶段，除了 frontend，还有 Middle end 和 Back end。
>
> 图片来源于 [wiki](https://en.wikipedia.org/wiki/Compiler)：
>
> ![Compiler design](https://upload.wikimedia.org/wikipedia/commons/thumb/c/cc/Compiler_design.svg/550px-Compiler_design.svg.png)
>
> Front end 主要的作用有：
>
> * 词法分析（lexing）
> * 语法分析（parsing）
> * 语义分析
>
> 将源代码翻译为 IR(Intermediate representation) 表示，即中间语言。
>
> Dart Kernel 就是 Dart 的 IR 表示。

Frontend Server 的源码位于 [flutter/engine/frontend_server](https://github.com/flutter/engine/tree/master/frontend_server) 中。

Frontend Server 是对 Dart Frontend Server 的包装，它用于将 Dart 源文件编译成 Dart Kernel binary (.dill-file)。

关于 Dart Kernel 的介绍可以阅读 [Kernel-Documentation](https://github.com/dart-lang/sdk/wiki/Kernel-Documentation)

Frontend Server 有两种运行模式：

* 即时模式，将 Dart 源文件作为参数提供给命令
* 交互模式，通过 stdin/stdout 进行通信，这也是 ResidentCompiler 中用的模式

Flutter 的 Frontend Server 是对 Dart Frontend 的简单包装，支持了即时模式和交互模式，处理逻辑的入口函数是 `server.starter()`。

如果存在 Dart 源文件作为额外参数，则使用即时模式直接调用 `FrontendCompiler.compile()` 方法，否则，则调用 `listenAndCompile()` 方法，监听回调处理：

``` dart
if (options.rest.isNotEmpty) {
  return await compiler.compile(options.rest[0], options) ? 0 : 254;
}

final Completer<int> completer = Completer<int>();
frontend.listenAndCompile(compiler, input ?? stdin, options, completer);
```

回调处理逻辑同样是委托给了 FrontendCompiler 实现，比如 `compile()` 和 `recompileDelta()` 等函数：

``` dart
@override
Future<bool> compile(String filename, ArgResults options, {IncrementalCompiler generator}) async {
    return _compiler.compile(filename, options, generator: generator);
}

@override
Future<Null> recompileDelta({String entryPoint}) async {
    return _compiler.recompileDelta(entryPoint: entryPoint);
}
```

关于 Dart Frontend 的实现就不在这篇文章的范围内了，有兴趣的同学可以去了解，相关源码位于 [dart/vm](https://github.com/dart-lang/sdk/tree/master/pkg/vm)。

## 容器初始化

热重载功能的实现可以主要分为两个部分：flutter_tools 生成增量包，并同步到设备上；设备上对视图进行刷新。主机（运行 flutter_tools）与设备的通信，依赖于通过 adb 建立的 RPC 通信。在设备处理 RPC 方法之前，需要先初始化 Flutter 运行的容器。接下来，我们以 Android 为例，来看看在设备上的初始化过程：

####  Java 层面

在 Java 上，默认会在 `Application.onCreat()` 函数中调用初始化方法：`FlutterMain.startInitialization(this)` ，初始化过程分为以下几个步骤：

 ##### initConfig

从 AndroidManifest 中获取自定义配置选项，可选配置有 `aot-shared-library-path`、`aot-snapshot-path` 等等：

``` java
if (metadata != null) {                                                                                                       
    sAotSharedLibraryPath = metadata.getString(PUBLIC_AOT_AOT_SHARED_LIBRARY_PATH, DEFAULT_AOT_SHARED_LIBRARY_PATH);          
    sAotVmSnapshotData = metadata.getString(PUBLIC_AOT_VM_SNAPSHOT_DATA_KEY, DEFAULT_AOT_VM_SNAPSHOT_DATA);                   
    sAotVmSnapshotInstr = metadata.getString(PUBLIC_AOT_VM_SNAPSHOT_INSTR_KEY, DEFAULT_AOT_VM_SNAPSHOT_INSTR);                
    sAotIsolateSnapshotData = metadata.getString(PUBLIC_AOT_ISOLATE_SNAPSHOT_DATA_KEY, DEFAULT_AOT_ISOLATE_SNAPSHOT_DATA);    
    sAotIsolateSnapshotInstr = metadata.getString(PUBLIC_AOT_ISOLATE_SNAPSHOT_INSTR_KEY, DEFAULT_AOT_ISOLATE_SNAPSHOT_INSTR); 
    sFlx = metadata.getString(PUBLIC_FLX_KEY, DEFAULT_FLX);                                                                   
    sFlutterAssetsDir = metadata.getString(PUBLIC_FLUTTER_ASSETS_DIR_KEY, DEFAULT_FLUTTER_ASSETS_DIR);                        
}                                                                                                                             
```

##### initAot

判断当前 Flutter 编译模式是 Blobs 还是 shared-library。

Blobs 属于 JIT 模式，由 Dart VM 执行，使用这种模式，会生成四个文件：`vm_snapshot_data`、`vm_snapshot_instr`、`isolate_snapshot_instr`、`isolate_snapshot_data` 这四个文件。

在 Flutter SDK 1.7.x 以下，默认会使用 Blobs 模式，也可以在构建命令后面添加 `--build-shared-library` 选项来使用 AOT 模式，完整命令为 `flutter build apk ----build-shared-library`，注意使用这种模式，需要 NDK 环境，最终会生成 app.so 文件。

##### initResources

Flutter 在 1.5.4 版本的时候是支持动态更新的，只需要在 AndroidManifest MetaData 中设置 `DynamicPatching` 为 True 即可，这里会实例化 ResourceUpdater 去处理，这块知识我们后面单独去讲。

``` java
if (metaData != null && metaData.getBoolean("DynamicPatching")) {                           
    sResourceUpdater = new ResourceUpdater(context);                                        
    // Also checking for ON_RESUME here since it's more efficient than waiting for actual   
    // onResume. Even though actual onResume is imminent when the app has just restarted,   
    // it's better to start downloading now, in parallel with the rest of initialization,   
    // and avoid a second application restart a bit later when actual onResume happens.     
    if (sResourceUpdater.getDownloadMode() == ResourceUpdater.DownloadMode.ON_RESTART ||    
        sResourceUpdater.getDownloadMode() == ResourceUpdater.DownloadMode.ON_RESUME) {     
        sResourceUpdater.startUpdateDownloadOnce();                                         
        if (sResourceUpdater.getInstallMode() == ResourceUpdater.InstallMode.IMMEDIATE) {   
            sResourceUpdater.waitForDownloadCompletion();                                   
        }                                                                                   
    }                                                                                       
}                                                                                           
```

Flutter 相关的资源文件和产物都会从 assets 中提取到应用的内部存储目录 app_flutter 中：

``` java
final String timestamp = checkTimestamp(dataDir);
// 时间戳，如果返回 null，则表示不需要更新
if (timestamp == null) {                                           
    return null;                                                   
}                                                                  
                                                                   
deleteFiles();                                                     
                                                                   
if (!extractUpdate(dataDir)) {                                     
    return null;                                                   
}                                                                  

// 提取文件
if (!extractAPK(dataDir)) {                                        
    return null;                                                   
}                                                                  
                                                                   
if (timestamp != null) {                                           
    try {
        // 记录时间戳
        new File(dataDir, timestamp).createNewFile();              
    } catch (IOException e) {                                      
        Log.w(TAG, "Failed to write resource timestamp");          
    }                                                              
}                                                                  
```

##### loadLibrary

准备好资源文件和产物后，最后加载 libflutter.so 文件：

``` java
System.loadLibrary("flutter"); 
```

##### ensureInitializationComplete

当我们启动一个 FlutterActivity 或 FlutterFragment 去渲染 Flutter 页面时，会在 `onCreate()` 函数中，调用 `FlutterMain.ensureInitializationComplete()` 方法：

``` java
 String appBundlePath = findAppBundlePath(applicationContext);                   
 String appStoragePath = PathUtils.getFilesDir(applicationContext);              
 String engineCachesPath = PathUtils.getCacheDirectory(applicationContext);
 // native 方法
 nativeInit(applicationContext, shellArgs.toArray(new String[0]),                
     appBundlePath, appStoragePath, engineCachesPath);                           
                                                                                 
 sInitialized = true;                                                            
```

#### native 层面

