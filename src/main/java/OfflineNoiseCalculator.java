import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.contrib.noise.NoiseConfigGroup;
import org.matsim.contrib.noise.NoiseOfflineCalculation;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

public class OfflineNoiseCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Noise Calculator...");

        // ==========================================
        // 0. SCENARIO SWITCHER (Change this value to 1, 2, or 3)
        // 1 = NO Gradient (Z=0), NO Barriers
        // 2 = WITH Gradient, NO Barriers
        // 3 = WITH Gradient, WITH Barriers
        // ==========================================
        int SCENARIO_ID = 1;

        System.out.println("=== RUNNING SCENARIO " + SCENARIO_ID + " ===");

        // ==========================================
        // 1. SETUP FILE PATHS
        // ==========================================
        String baseDir = "D:/Michael_Thesis/data/indicators/noise/";
        String outputDir = baseDir + "run" + SCENARIO_ID + "/";
        new File(outputDir).mkdirs();

        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/munich_1pct_network_connected_3d_hbefa.xml.gz";
        String originalEventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output_munich/ITERS/it.115/115.events.xml.gz";
        String populationFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output_munich/output_plans.xml.gz";
        String patchedPopulationFile = outputDir + "patched_plans.xml.gz";

        String receiversFile = "D:/Michael_Thesis/data/indicators/noise/Receiver points.csv";
        String buildingsFile = "D:/Michael_Thesis/data/bavaria/buildings LoD2_munich_trial 2/buildings_lod2.geojson";
        String vehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output_munich/output_vehicles.xml.gz";

        // ==========================================
        // 2. PATCH POPULATION FILE (ATLANTIS -> EPSG:25832)
        // ==========================================
        File patchedFile = new File(patchedPopulationFile);
        if (patchedFile.exists()) {
            System.out.println("Deleting previous patched file...");
            patchedFile.delete();
        }

        System.out.println("Brute-forcing ATLANTIS CRS patch in Population file...");
        try (java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(new java.util.zip.GZIPInputStream(new java.io.FileInputStream(populationFile))));
             java.io.BufferedWriter writer = new java.io.BufferedWriter(new java.io.OutputStreamWriter(new java.util.zip.GZIPOutputStream(new java.io.FileOutputStream(patchedPopulationFile))))) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.toLowerCase().contains("atlantis")) {
                    line = line.replaceAll("(?i)ATLANTIS", "EPSG:25832");
                }
                writer.write(line);
                writer.newLine();
            }
            System.out.println("Population file brute-force patched successfully!");
        } catch (Exception e) {
            System.out.println("Error patching population file: " + e.getMessage());
        }

        // ==========================================
        // 3. PREPARE EVENTS FILE FOR MATSIM
        // ==========================================
        String expectedEventsFile = outputDir + "output_events.xml.gz";
        try {
            System.out.println("Copying events file to " + outputDir + " ...");
            Files.copy(Paths.get(originalEventsFile), Paths.get(expectedEventsFile), StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception e) {
            System.out.println("Warning: Failed to copy events file. It might already exist.");
        }

        // ==========================================
        // 4. CONFIGURE MATSIM & NOISE PARAMETERS
        // ==========================================
        Config config = ConfigUtils.createConfig();
        config.controler().setOutputDirectory(outputDir);
        config.global().setCoordinateSystem("EPSG:25832");

        NoiseConfigGroup noiseConfig = new NoiseConfigGroup();
        noiseConfig.setReceiverPointsCSVFileCoordinateSystem("EPSG:25832");
        noiseConfig.setReceiverPointsCSVFile(receiversFile);
        noiseConfig.setTimeBinSizeNoiseComputation(3600);
        noiseConfig.setComputeCausingAgents(false);
        noiseConfig.setComputeNoiseDamages(true);
        noiseConfig.setInternalizeNoiseDamages(false);
        noiseConfig.setNoiseComputationMethod(NoiseConfigGroup.NoiseComputationMethod.RLS19);
        noiseConfig.setNoiseAllocationApproach(NoiseConfigGroup.NoiseAllocationApproach.AverageCost);
        noiseConfig.setScaleFactor(100.0);

        // Apply Scenario-specific Barrier Logic
        if (SCENARIO_ID == 3) {
            System.out.println("Configuring Noise Barriers (Buildings)...");
            noiseConfig.setConsiderNoiseBarriers(true);
            noiseConfig.setNoiseBarriersSourceCRS("EPSG:25832");
            noiseConfig.setNoiseBarriersFilePath(buildingsFile);
        } else {
            System.out.println("Noise Barriers Disabled.");
            noiseConfig.setConsiderNoiseBarriers(false);
        }

        config.addModule(noiseConfig);

        // ==========================================
        // 5. LOAD SCENARIO & APPLY GRADIENT LOGIC
        // ==========================================
        config.network().setInputFile(networkFile);
        config.plans().setInputFile(patchedPopulationFile);
        config.vehicles().setVehiclesFile(vehiclesFile);

        Scenario scenario = ScenarioUtils.loadScenario(config);
        scenario.getConfig().controler().setOutputDirectory(outputDir);

        if (SCENARIO_ID == 1) {
            System.out.println("Removing GRADIENT attributes to disable slope effects...");
            for (Link link : scenario.getNetwork().getLinks().values()) {
                if (link.getAttributes().getAttribute("GRADIENT") != null) {
                    link.getAttributes().putAttribute("GRADIENT", 0.0); // Force the gradient to 0.0 to neutralize RLS-19 calculations
                }
            }
        } else {
            System.out.println("Preserving GRADIENT attributes (Slope Active).");
        }

        // ==========================================
        // 6. EXECUTE OFFLINE CALCULATION
        // ==========================================
        System.out.println("Starting MATSim Offline Noise Calculation...");
        NoiseOfflineCalculation noiseCalculation = new NoiseOfflineCalculation(scenario, outputDir);
        noiseCalculation.run();

        System.out.println("Noise calculation for Scenario " + SCENARIO_ID + " completed! Results are saved in: " + outputDir);
    }
}