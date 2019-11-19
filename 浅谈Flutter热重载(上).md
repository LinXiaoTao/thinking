## 更新记录

* 本文完成于 本文写于 2019.09.10，Flutter SDK 版本为 v1.5.4-hotfix.2
* 2019.09.12 更新，将**差异包**字眼变更为**增量包**
* 2019.09.12 更新，**--not-hot** 写错，应该为 **--no-hot**

## 前言

这是浅谈 Flutter 系列的第二篇，上一篇是 [浅谈Flutter构建](https://juejin.im/post/5d68fb1af265da03d063b69e)，在上一篇中，主要是理清 Flutter 在 debug 和 release 模式下生成的不同产物分别是什么，怎么调试 build_tools 源码等等，这些不会在后面重复讨论，所以有需要的同学可以先看下第一篇。

热重载是 Flutter 的一个大杀器，非常受欢迎，特别是对于客户端开发的同学来说，项目大了以后，可能就会出现，代码改一行，构建半小时的场面。之前非常火热的组件化方案其实一点就是为了解决构建时间过长的痛点。而对于 Flutter 来说，有两种模式可以快速应用修改：hot reload（热重载）和 hot restart（热重启），其中 hot reload 只需要几百毫秒就可以完成更新，速度非常快，hot restart 稍微慢一点，需要秒单位。在修改了资源文件或需要重新构建状态，只能使用 hot restart。

## 源码解析

在第一篇文章中，我们说到，对于每个 Flutter 命令，都有一个 Command 类与之对应，我们使用的 `flutter run` 是由 RunCommand 类处理的。

默认在 debug 模式下会开启 hot mode，release 模式下默认关闭，可以在执行 run 命令的时候，添加 `--no-hot` 来禁用 hot mode。

当启用 hot mode 时，会使用 HotRunner 来启动 Flutter 应用。

``` dart
if (hotMode) {                                          
  runner = HotRunner(                                   
    flutterDevices,                                     
    target: targetFile,                                 
    debuggingOptions: _createDebuggingOptions(),        
    benchmarkMode: argResults['benchmark'],             
    applicationBinary: applicationBinaryPath == null    
        ? null                                          
        : fs.file(applicationBinaryPath),               
    projectRootPath: argResults['project-root'],        
    packagesFilePath: globalResults['packages'],        
    dillOutputPath: argResults['output-dill'],          
    saveCompilationTrace: argResults['train'],          
    stayResident: stayResident,                         
    ipv6: ipv6,                                         
  );                                                    
} 
```

hot mode 开启后，首先会进行初始化，这部分相关的代码在 `HotRunner run()`。

### 初始化

* 构建应用，以 Anroid 为例，这里会调用 gradle 去执行 assemble task 来生成 APK 文件

  ``` dart
  if (!prebuiltApplication || androidSdk.licensesAvailable && androidSdk.latestVersion == null) {   
    printTrace('Building APK');                                                                     
    final FlutterProject project = FlutterProject.current();                                        
    await buildApk(                                                                                 
        project: project,                                                                           
        target: mainPath,                                                                           
        androidBuildInfo: AndroidBuildInfo(debuggingOptions.buildInfo,                              
          targetArchs: <AndroidArch>[androidArch]                                                   
        ),                                                                                           
    );                                                                                              
    // Package has been built, so we can get the updated application ID and                         
    // activity name from the .apk.                                                                 
    package = await AndroidApk.fromAndroidProject(project.android);                                 
  }                                                                                                 
  ```

* 构建 APK 成功，则会使用 adb 启动它，并建立 sockets 连接，转发主机的端口到设备上。

  > 这里的主机指的是，运行 Flutter 命令的环境，一般是 PC。设备指的是，运行 Flutter 应用的环境，这里指手机。

  转发端口的意义是为了与设备上 Dart VM（虚拟机）进行通信，这个后面会说到。

  在使用 adb 启动应用后，会监听 log 输出，使用正则表达式去获取 sockets 连接地址后，设置端口转发。

  ``` dart
  void _handleLine(String line) {                                                                                  
    Uri uri;                                                                                                       
    final RegExp r = RegExp('${RegExp.escape(serviceName)} listening on ((http|\/\/)[a-zA-Z0-9:/=_\\-\.\\[\\]]+)');
    final Match match = r.firstMatch(line);                                                                        
                                                                                                                   
    if (match != null) {                                                                                           
      try {                                                                                                        
        uri = Uri.parse(match[1]);                                                                                 
      } catch (error) {                                                                                            
        _stopScrapingLogs();                                                                                       
        _completer.completeError(error);                                                                           
      }                                                                                                            
    }                                                                                                              
                                                                                                                   
    if (uri != null) {                                                                                             
      assert(!_completer.isCompleted);                                                                             
      _stopScrapingLogs();                                                                                         
      _completer.complete(_forwardPort(uri));                                                                      
    }                                                                                                              
                                                                                                                   
  }
  
  // 转发端口
  Future<Uri> _forwardPort(Uri deviceUri) async {                                                         
    printTrace('$serviceName URL on device: $deviceUri');                                                 
    Uri hostUri = deviceUri;                                                                              
                                                                                                          
    if (portForwarder != null) {                                                                          
      final int actualDevicePort = deviceUri.port;                                                        
      final int actualHostPort = await portForwarder.forward(actualDevicePort, hostPort: hostPort);       
      printTrace('Forwarded host port $actualHostPort to device port $actualDevicePort for $serviceName');
      hostUri = deviceUri.replace(port: actualHostPort);                                                  
    }                                                                                                     
                                                                                                          
    assert(InternetAddress(hostUri.host).isLoopback);                                                     
    if (ipv6) {                                                                                           
      hostUri = hostUri.replace(host: InternetAddress.loopbackIPv6.host);                                 
    }                                                                                                     
                                                                                                          
    return hostUri;                                                                                       
  }                                                                                                       
  ```

  在我的设备上，匹配地址如下：

  ``` 
  09-08 14:14:12.708  6122  6149 I flutter : Observatory listening on http://127.0.0.1:45093/6p_NsmXILHw=/
  ```

* 根据第二步建立的 sockets 连接地址和转发的端口，建立 RPC 通信，这里使用的 [json_rpc_2](https://github.com/dart-lang/json_rpc_2) 。

  > 关于 Dart VM 支持的 RPC 方法可以看这里：[Dart VM Service Protocol 3.26](https://github.com/dart-lang/sdk/blob/master/runtime/vm/service/service.md)
  >
  > 关于 JSON-RPC，可以看这里：[JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
  >
  > 注意：Dart VM 只支持 WebSocket，不支持 HTTP。
  >
  > "The VM will start a webserver which services protocol requests via WebSocket. It is possible to make HTTP (non-WebSocket) requests, but this does not allow access to VM *events* and is not documented here."

  ``` dart
  static Future<VMService> connect(                                                                            
    Uri httpUri, {                                                                                             
    ReloadSources reloadSources,                                                                               
    Restart restart,                                                                                           
    CompileExpression compileExpression,                                                                       
    io.CompressionOptions compression = io.CompressionOptions.compressionDefault,                              
  }) async {                                                                                                   
    final Uri wsUri = httpUri.replace(scheme: 'ws', path: fs.path.join(httpUri.path, 'ws'));                   
    final StreamChannel<String> channel = await _openChannel(wsUri, compression: compression);                 
    final rpc.Peer peer = rpc.Peer.withoutJson(jsonDocument.bind(channel), onUnhandledError: _unhandledError); 
    final VMService service = VMService(peer, httpUri, wsUri, reloadSources, restart, compileExpression);      
    // This call is to ensure we are able to establish a connection instead of                                 
    // keeping on trucking and failing farther down the process.                                               
    await service._sendRequest('getVersion', const <String, dynamic>{});                                       
    return service;                                                                                            
  }                                                                                                            
  ```

  关于 Dart VM 具体的使用，可以看 `FlutterDevice.getVMs()` 和 `FlutterDevice.refreshViews()` 两个函数。
  
  `getVMs()` 用于获取 Dart VM 实例，最终调用的是 **getVM** 这个 RPC 方法：
  
  ``` dart
  @override                                                             
  Future<Map<String, dynamic>> _fetchDirect() => invokeRpcRaw('getVM'); 
  ```
  
  ![getVM](https://user-gold-cdn.xitu.io/2019/9/9/16d14e728a12328b?w=904&h=184&f=png&s=19281)
  
  `refreshVIews()` 用于获取最新的 FlutterView 实例，最终调用的是 **_flutter.listViews** 这个 RPC 方法：
  
  ``` dart
  // When the future returned by invokeRpc() below returns,              
  // the _viewCache will have been updated.                              
  // This message updates all the views of every isolate.                
  await vmService.vm.invokeRpc<ServiceObject>('_flutter.listViews');     
  ```
  
  这个方法不属于 Dart VM 定义的，是 Flutter 额外扩展的方法，定义位于 [Engine-specific-Service-Protocol-extensions](https://github.com/flutter/flutter/wiki/Engine-specific-Service-Protocol-extensions)：
  
  ![listViews](https://user-gold-cdn.xitu.io/2019/9/9/16d14ec3de2b95e0?w=747&h=535&f=png&s=61996)
  
* 这是初始化的最后一步，使用 devfs 管理设备文件，当执行热重载时，会重新生成增量包再同步到设备上。

  首先，会在设备上生成一个目录，用于存放重载的资源文件和增量包。

  ``` dart
  @override                                                                             
  Future<Uri> create(String fsName) async {                                             
    final Map<String, dynamic> response = await vmService.vm.createDevFS(fsName);       
    return Uri.parse(response['uri']);                                                  
  }                                                                               
  
  /// Create a new development file system on the device.                             
  Future<Map<String, dynamic>> createDevFS(String fsName) {                           
    return invokeRpcRaw('_createDevFS', params: <String, dynamic>{'fsName': fsName}); 
  }                                                                                   
  ```

  生成的 Uri 类似这种：file:///data/user/0/com.example.my_app/code_cache/my_appLGHJYJ/my_app/，每个 FlutterDevice 都会有个 `DevFS devFS` 用于封装对设备文件的同步。设备上创建的目录如下：

  ![code_cache](https://user-gold-cdn.xitu.io/2019/9/9/16d154533a74184f?w=429&h=170&f=png&s=17910)

  每执行一次 `flutter run` 都会生成一个新的 `my_appXXXX` 目录，修改的资源都会同步到这个目录中。
  
  > 注意这里我是用的测试项目 my_app
  
  在生成目录后，会同步一次资源文件，将 fonts、packages、AssetManifest.json 等同步到设备中。
  
  ``` dart
  final UpdateFSReport devfsResult = await _updateDevFS(fullRestart: true);
  ```
  
  ![code_cache_my_app](https://user-gold-cdn.xitu.io/2019/9/9/16d15520be20309e?w=463&h=213&f=png&s=24775)

### 监听输入

当修改了 dart 代码后，我们需要输入 r 或者 R 来使得我们的修改生效，其中 r 表示 hot reload，R 表示 hot restart。

首先，需要先注册输入处理函数：

``` dart
void setupTerminal() {                               
  assert(stayResident);                              
  if (usesTerminalUI) {                              
    if (!logger.quiet) {                             
      printStatus('');                               
      printHelp(details: false);                     
    }                                                
    terminal.singleCharMode = true;                  
    terminal.keystrokes.listen(processTerminalInput);
  }                                                  
}                                                    
```

当输入 r 时，最终会调用到 `restart(false)` 这个方法：

``` dart
if (lower == 'r') {                                                             
  OperationResult result;                                                       
  if (code == 'R') {                                                            
    // If hot restart is not supported for all devices, ignore the command.     
    if (!canHotRestart) {                                                       
      return;                                                                   
    }                                                                           
    result = await restart(fullRestart: true);                                  
  } else {                                                                      
    result = await restart(fullRestart: false);                                 
  }                                                                             
  if (!result.isOk) {                                                           
    printStatus('Try again after fixing the above error(s).', emphasis: true);  
  }                                                                             
}                                                     
```

`restart()` 函数的核心代码在 `_reloadSources()` 函数中，这个函数的主要作用如下：

* 调用 `_updateDevFS()` 方法，生成增量包，并同步到设备上，DevFS 用于管理设备文件系统。

  首先比较资源文件的修改时间，判断是否需要更新：

  ``` dart
  // Only update assets if they have been modified, or if this is the      
  // first upload of the asset bundle.                                     
  if (content.isModified || (bundleFirstUpload && archivePath != null)) {  
    dirtyEntries[deviceUri] = content;                                     
    syncedBytes += content.size;                                           
    if (archivePath != null && !bundleFirstUpload) {                       
      assetPathsToEvict.add(archivePath);                                  
    }                                                                      
  }                                                                        
  ```

  dirtyEntries 用于存放需要更新的内容，syncedBytes 计算需要同步的字节数。

  接着，生成代码增量包，以 .incremental.dill 结尾：

  ``` dart
  final CompilerOutput compilerOutput = await generator.recompile(                                              
    mainPath,                                                                                                   
    invalidatedFiles,                                                                                           
    outputPath:  dillOutputPath ?? getDefaultApplicationKernelPath(trackWidgetCreation: trackWidgetCreation),   
    packagesFilePath : _packagesFilePath,                                                                       
  );                                                                                                            
  ```

  最后通过 http 写入到设备中：

  ``` dart
  if (dirtyEntries.isNotEmpty) {                                                        
    try {                                                                               
      await _httpWriter.write(dirtyEntries);                                            
    } on SocketException catch (socketException, stackTrace) {                          
      printTrace('DevFS sync failed. Lost connection to device: $socketException');     
      throw DevFSException('Lost connection to device.', socketException, stackTrace);  
    } catch (exception, stackTrace) {                                                   
      printError('Could not update files on device: $exception');                       
      throw DevFSException('Sync failed', exception, stackTrace);                       
    }                                                                                   
  }                                                                                     
  ```

* 调用 `reloadSources()` 方法通知 Dart VM 重新加载 Dart 增量包，同样的这里也是调用的 RPC 方法：

  ``` dart
  final Map<String, dynamic> arguments = <String, dynamic>{                                      
    'pause': pause,                                                                              
  };                                                                                             
  if (rootLibUri != null) {                                                                      
    arguments['rootLibUri'] = rootLibUri.toString();                                             
  }                                                                                              
  if (packagesUri != null) {                                                                     
    arguments['packagesUri'] = packagesUri.toString();                                           
  }                                                                                              
  final Map<String, dynamic> response = await invokeRpcRaw('_reloadSources', params: arguments); 
  return response;                                                                               
  ```

* 最后调用 `flutterReassemble()` 方法重新刷新页面，这里调用的是 RPC 方法 **ext.flutter.reassemble**：

  ``` dart
  Future<Map<String, dynamic>> flutterReassemble() {                
    return invokeFlutterExtensionRpcRaw('ext.flutter.reassemble');  
  }                                                                 
  ```

## 关于增量包

我们用一个非常简单的 DEMO 来看下生成的增量包的内容。DEMO 有两个 dart 文件，首先是 main.dart，这个是入口文件：

``` dart
void main() => runApp(MyApp());          
                                         
class MyApp extends StatelessWidget {    
  @override                              
  Widget build(BuildContext context) {   
    return MaterialApp(                  
      title: 'Flutter Demo',             
      theme: ThemeData(                  
        primarySwatch: Colors.blue,      
      ),                                 
      home: HomePage(),                  
    );                                   
  }                                      
}                                        
```

home.dart 也非常简单，就显示一个文本：

``` dart
class HomePage extends StatelessWidget {   
  @override                                
  Widget build(BuildContext context) {     
    return Scaffold(                       
      body: Center(                        
        child: Text('Hello World'),        
      ),                                   
      appBar: AppBar(                      
        title: Text('My APP'),             
      ),                                   
    );                                     
  }                                        
}                                          
```

这里我们做两个地方的修改，首先是将主题颜色从 `Colors.blue` 改成 `Colors.red`，将 HomePage 中的 "Hello World" 改成 "Hello Flutter"。

修改完成后，在终端键入 r 后执行，会在 build 目录下生成 app.dill.incremental.dill，什么是 dill 文件？其实这里面就是我们的代码产物，用于提供给 Dart VM 执行的。我们用 `strings` 命令查看下内容：

![incremental.dill](https://user-gold-cdn.xitu.io/2019/9/9/16d162fd0eda5b3e?w=804&h=928&f=png&s=941410)

修改的内容已经包含在增量包中了，当我们执行 `_updateDevFS()` 方法后，incremental.dill 也被同步到设备中了。

![app_incremental_dill](https://user-gold-cdn.xitu.io/2019/9/9/16d1633c7395161b?w=758&h=354&f=png&s=46822)

名字虽然不一样，但内容一致的。现在设备是已经包含了增量包，接着下来就是通知 Dart VM 刷新了，先调用 `reloadSources()`，最后调用 `flutterReassemble()`，执行完之后，我们就可以看到新的界面了。

![new_ui](https://user-gold-cdn.xitu.io/2019/9/9/16d1643f1380ac04?w=608&h=1086&f=png&s=97611)

## 总结

热重载功能的实现，首先是增量包的实现，这里我们没有细讲，留到后面的文章中，生成的增量包，文件后缀以 incremental.dill 结尾，文件的同步则通过 adb 建立的 sockets 连接进行传输，而且这个 sockets 另外一个非常重要的功能就是，建立和 Dart VM 的 RPC 通信，Dart VM 本身就已经定义了一些 RPC 方法，Flutter 又扩展了一些，获取 Dart VM 信息，刷新 Flutter 视图等等都是通过 RPC 实现的。

因为篇幅的原因，这里我们并没有讲解增量包的生成实现，还有 Dart VM 和 Flutter engine 对 RPC 方法的实现，这个留到后面的文章。

写到这里，其实距离实现动态更新的目标也越来越清晰，第一，生成增量包；第二，在合适的时候，重新加载刷新增量包。















