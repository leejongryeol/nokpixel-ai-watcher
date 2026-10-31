/*
 * Pixel Dungeon
 * Copyright (C) 2012-2015 Oleg Dolya
 *
 * Shattered Pixel Dungeon
 * Copyright (C) 2014-2026 Evan Debenham
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>
 */

package com.shatteredpixel.shatteredpixeldungeon.desktop;

import com.badlogic.gdx.Files;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3Application;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3ApplicationConfiguration;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3FileHandle;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3Preferences;
import com.badlogic.gdx.utils.Architecture;
import com.badlogic.gdx.utils.Os;
import com.badlogic.gdx.utils.SharedLibraryLoader;
import com.shatteredpixel.shatteredpixeldungeon.SPDSettings;
import com.shatteredpixel.shatteredpixeldungeon.ShatteredPixelDungeon;
import com.shatteredpixel.shatteredpixeldungeon.services.news.News;
import com.shatteredpixel.shatteredpixeldungeon.services.news.NewsImpl;
import com.shatteredpixel.shatteredpixeldungeon.services.updates.UpdateImpl;
import com.shatteredpixel.shatteredpixeldungeon.services.updates.Updates;
import com.watabou.noosa.Game;
import com.watabou.utils.FileUtils;
import com.watabou.utils.Point;

import org.lwjgl.util.tinyfd.TinyFileDialogs;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Locale;

public class DesktopLauncher {

	// [nokpixel-ai-watcher] AI 관찰용 세로(9:16) 고정 창 크기. {모니터 세로 해상도, 창 가로, 창 세로, 배율}
	// 창 ÷ 배율이 모두 180x320이라 세 크기의 시야(보이는 칸 수)가 같다. ai-bridge/agent.py의 DISPLAY_PRESETS와 같은 값.
	private static final int[][] AI_WINDOW_PRESETS = {
			{1440, 720, 1280, 4},
			{1080, 540, 960, 3},
			{768, 360, 640, 2},
	};
	private static final int AI_WINDOW_MARGIN = 120; // 제목 표시줄 + 작업 표시줄 여유

	// 실행 옵션 --display=1440|1080|768 이 있으면 그 크기, 없으면 모니터 세로 해상도에 들어가는 가장 큰 크기
	private static int[] aiWindowPreset( String[] args ){
		for (String arg : args){
			if (arg.startsWith("--display=")){
				for (int[] preset : AI_WINDOW_PRESETS){
					if (arg.equals("--display=" + preset[0])) return preset;
				}
			}
		}
		int screenHeight = Lwjgl3ApplicationConfiguration.getDisplayMode().height;
		for (int[] preset : AI_WINDOW_PRESETS){
			if (preset[2] + AI_WINDOW_MARGIN <= screenHeight) return preset;
		}
		return AI_WINDOW_PRESETS[AI_WINDOW_PRESETS.length - 1];
	}

	public static void main (String[] args) {

		if (!DesktopLaunchValidator.verifyValidJVMState(args)){
			return;
		}

		//detection for FreeBSD (which is equivalent to linux for us)
		//TODO might want to merge request this to libGDX
		if (System.getProperty("os.name").contains("FreeBSD")) {
			SharedLibraryLoader.os = Os.Linux;
			//this overrides incorrect values set in SharedLibraryLoader's static initializer
			if (System.getProperty("os.arch").contains("64") || System.getProperty("os.arch").startsWith("armv8")){
				SharedLibraryLoader.bitness = Architecture.Bitness._64;
			}
		}
		
		final String title;
		if (DesktopLauncher.class.getPackage().getSpecificationTitle() == null){
			title = System.getProperty("Specification-Title");
		} else {
			title = DesktopLauncher.class.getPackage().getSpecificationTitle();
		}
		
		Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {
			@Override
			public void uncaughtException(Thread thread, Throwable throwable) {
				Game.reportException(throwable);
				StringWriter sw = new StringWriter();
				PrintWriter pw = new PrintWriter(sw);
				throwable.printStackTrace(pw);
				pw.flush();
				String exceptionMsg = sw.toString();

				//shorten/simplify exception message to make it easier to fit into a message box
				exceptionMsg = exceptionMsg.replaceAll("\\(.*:([0-9]*)\\)", "($1)");
				exceptionMsg = exceptionMsg.replace("com.shatteredpixel.shatteredpixeldungeon.", "");
				exceptionMsg = exceptionMsg.replace("com.watabou.", "");
				exceptionMsg = exceptionMsg.replace("com.badlogic.gdx.", "");
				exceptionMsg = exceptionMsg.replace("\t", "  "); //shortens length of tabs

				//replace ' and " with similar equivalents as tinyfd hates them for some reason
				exceptionMsg = exceptionMsg.replace('\'', '’');
				exceptionMsg = exceptionMsg.replace('"', '”');

				if (exceptionMsg.length() > 1000){
					exceptionMsg = exceptionMsg.substring(0, 1000) + "...";
				}

				if (exceptionMsg.contains("Couldn’t create window")){
					TinyFileDialogs.tinyfd_messageBox(title + " Has Crashed!",
							title + " was not able to initialize its graphics display, sorry about that!\n\n" +
									"This usually happens when your graphics card has misconfigured drivers or does not support openGL 2.0+.\n\n" +
									"If you are certain the game should work on your computer, please message the developer (Evan@ShatteredPixel.com)\n\n" +
									"version: " + Game.version + "\n" +
									exceptionMsg,
							"ok", "error", false);
				} else {
					TinyFileDialogs.tinyfd_messageBox(title + " Has Crashed!",
							title + " has run into an error it cannot recover from and has crashed, sorry about that!\n\n" +
									"If you could, please email this error message to the developer (Evan@ShatteredPixel.com):\n\n" +
									"version: " + Game.version + "\n" +
									exceptionMsg,
							"ok", "error", false);
				}
				System.exit(1);
			}
		});
		
		Game.version = DesktopLauncher.class.getPackage().getSpecificationVersion();
		if (Game.version == null) {
			Game.version = System.getProperty("Specification-Version");
		}
		
		try {
			Game.versionCode = Integer.parseInt(DesktopLauncher.class.getPackage().getImplementationVersion());
		} catch (NumberFormatException e) {
			Game.versionCode = Integer.parseInt(System.getProperty("Implementation-Version"));
		}

		if (UpdateImpl.supportsUpdates()){
			Updates.service = UpdateImpl.getUpdateService();
		}
		if (NewsImpl.supportsNews()){
			News.service = NewsImpl.getNewsService();
		}
		
		Lwjgl3ApplicationConfiguration config = new Lwjgl3ApplicationConfiguration();
		
		config.setTitle( title );

		//if I were implementing this from scratch I would use the full implementation title for saves
		// (e.g. /.shatteredpixel/shatteredpixeldungeon), but we have too much existing save
		// date to worry about transferring at this point.
		String vendor = DesktopLauncher.class.getPackage().getImplementationTitle();
		if (vendor == null) {
			vendor = System.getProperty("Implementation-Title");
		}
		vendor = vendor.split("\\.")[1];

		String basePath = "";
		Files.FileType baseFileType = null;
		if (SharedLibraryLoader.os == Os.Windows) {
			if (System.getProperties().getProperty("os.name").equals("Windows XP")) {
				basePath = "Application Data/." + vendor + "/" + title + "/";
			} else {
				basePath = "AppData/Roaming/." + vendor + "/" + title + "/";
			}
			baseFileType = Files.FileType.External;
		} else if (SharedLibraryLoader.os == Os.MacOsX) {
			basePath = "Library/Application Support/" + title + "/";
			baseFileType = Files.FileType.External;
		} else if (SharedLibraryLoader.os == Os.Linux) {
			String XDGHome = System.getenv("XDG_DATA_HOME");
			if (XDGHome == null) XDGHome = System.getProperty("user.home") + "/.local/share";

			String titleLinux = title.toLowerCase(Locale.ROOT).replace(" ", "-");
			basePath = XDGHome + "/." + vendor + "/" + titleLinux + "/";

			baseFileType = Files.FileType.Absolute;
		}

		config.setPreferencesConfig( basePath, baseFileType );
		SPDSettings.set( new Lwjgl3Preferences( new Lwjgl3FileHandle(basePath + SPDSettings.DEFAULT_PREFS_FILE, baseFileType) ));
		FileUtils.setDefaultFileProperties( baseFileType, basePath );
		
		// [nokpixel-ai-watcher] AI 관찰용: 창을 세로(9:16) 고정 크기로 띄운다.
		// 모바일 화면 배치와 배율을 함께 고정해야 세 크기의 시야가 같다.
		// (그냥 두면 PC용 넓은 화면이 켜지거나 모니터 밀도에 따라 배율이 달라진다. PixelScene.create() 참고)
		// SPDSettings.fullscreen()은 화면 갱신(platform, Gdx.app)까지 부르는데 둘 다 아직 없으므로 값만 저장한다.
		int[] preset = aiWindowPreset( args );
		int windowWidth = preset[1], windowHeight = preset[2];
		SPDSettings.put( SPDSettings.KEY_FULLSCREEN, false );
		SPDSettings.windowMaximized( false );
		SPDSettings.windowResolution( new Point( windowWidth, windowHeight ) );
		SPDSettings.interfaceSize( 0 );
		SPDSettings.scale( preset[3] );
		config.setWindowSizeLimits( windowWidth, windowHeight, windowWidth, windowHeight );
		config.setWindowedMode( windowWidth, windowHeight );
		config.setResizable( false );

		config.setMaximized( false );

		//going fullscreen on launch is a bit buggy
		// so game always starts windowed and then switches in DesktopPlatformSupport.updateSystemUI
		//config.setFullscreenMode(Lwjgl3ApplicationConfiguration.getDisplayMode());

		//records whether window is maximized or not for settings
		DesktopWindowListener listener = new DesktopWindowListener();
		config.setWindowListener( listener );
		
		config.setWindowIcon("icons/icon_16.png", "icons/icon_32.png", "icons/icon_48.png",
				"icons/icon_64.png", "icons/icon_128.png", "icons/icon_256.png");

		new Lwjgl3Application(new ShatteredPixelDungeon(new DesktopPlatformSupport()), config);
	}
}
