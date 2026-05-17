import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.contrib.emissions.EmissionModule;
import org.matsim.contrib.emissions.events.ColdEmissionEvent;
import org.matsim.contrib.emissions.events.ColdEmissionEventHandler;
import org.matsim.contrib.emissions.events.WarmEmissionEvent;
import org.matsim.contrib.emissions.events.WarmEmissionEventHandler;
import org.matsim.contrib.emissions.utils.EmissionsConfigGroup;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.MatsimEventsReader;
import org.matsim.core.scenario.ScenarioUtils;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.IOException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class OfflineEmissionCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Emission Calculator...");

        // ==========================================
        // 1. DEFINE PATHS
        // ==========================================
        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/munich_1pct_network_connected_3d_hbefa.xml.gz";
        String eventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output_munich/ITERS/it.115/115.events.xml.gz";
        String vehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output_munich/output_vehicles.xml.gz";

        String hbefaHotFile = "D:/Michael_Thesis/data/hbefa/EFA_HOT_Vehcat_reformat.csv";
        String hbefaColdFile = "D:/Michael_Thesis/data/hbefa/EFA_ColdStart_Vehcat_michael_thesis_weighted_v4_2.csv";

        String outputTotalFile = "D:/Michael_Thesis/data/indicators/emissions_munich/emissions_per_link_total.csv";
        String outputHotColdFile = "D:/Michael_Thesis/data/indicators/emissions_munich/emissions_per_link_hot_cold.csv";

        // ==========================================
        // 2. CONFIGURE MATSIM & EMISSIONS MODULE
        // ==========================================
        System.out.println("Setting up configurations...");
        Config config = ConfigUtils.createConfig();
        config.network().setInputFile(networkFile);
        config.vehicles().setVehiclesFile(vehiclesFile);

        EmissionsConfigGroup emissionsConfig = new EmissionsConfigGroup();
        emissionsConfig.setAverageWarmEmissionFactorsFile(hbefaHotFile);
        emissionsConfig.setAverageColdEmissionFactorsFile(hbefaColdFile);
        emissionsConfig.setEmissionsComputationMethod(EmissionsConfigGroup.EmissionsComputationMethod.AverageSpeed);
        emissionsConfig.setDetailedVsAverageLookupBehavior(EmissionsConfigGroup.DetailedVsAverageLookupBehavior.directlyTryAverageTable);
        emissionsConfig.setHbefaVehicleDescriptionSource(EmissionsConfigGroup.HbefaVehicleDescriptionSource.fromVehicleTypeDescription);
        emissionsConfig.setNonScenarioVehicles(EmissionsConfigGroup.NonScenarioVehicles.valueOf("ignore"));

        config.addModule(emissionsConfig);

        // ==========================================
        // 3. LOAD SCENARIO
        // ==========================================
        System.out.println("Loading 3D Network and Vehicles into memory...");
        Scenario scenario = ScenarioUtils.loadScenario(config);

        System.out.println("Validating custom HBEFA attributes from XML...");
        int missingCount = 0;
        for (Link link : scenario.getNetwork().getLinks().values()) {
            if (link.getAttributes().getAttribute("hbefa_road_type") == null) {
                missingCount++;
            }
        }
        if (missingCount > 0) {
            System.out.println("WARNING: " + missingCount + " links are missing the custom HBEFA attribute!");
        }

        // ==========================================
        // 4. PREPARE THE EVENTS MANAGER & CUSTOM AGGREGATOR
        // ==========================================
        EventsManager eventsManager = EventsUtils.createEventsManager();
        new EmissionModule(scenario, eventsManager);

        LinkEmissionAggregator aggregator = new LinkEmissionAggregator();
        eventsManager.addHandler(aggregator);

        // ==========================================
        // 5. RUN THE OFFLINE PLAYBACK
        // ==========================================
        System.out.println("Playing back events from last iteration...");
        MatsimEventsReader reader = new MatsimEventsReader(eventsManager);
        reader.readFile(eventsFile);

        // ==========================================
        // 6. EXPORT TO CSV
        // ==========================================
        System.out.println("Exporting spatial emission data to CSVs...");
        aggregator.writeToCsv(outputTotalFile, scenario.getNetwork(), "TOTAL");
        aggregator.writeToCsv(outputHotColdFile, scenario.getNetwork(), "HOT_COLD");

        System.out.println("Pipeline execution completed successfully.");
    }

    private static class LinkEmissionAggregator implements WarmEmissionEventHandler, ColdEmissionEventHandler {

        // Data structure: Map<LinkId, Map<Condition_Pollutant, TotalAmount>>
        // Example inner key: "HOT|HC", "COLD|NOx"
        private final Map<Id<Link>, Map<String, Double>> linkEmissions = new HashMap<>();

        @Override
        public void handleEvent(WarmEmissionEvent event) {
            processEmission(event.getLinkId(), event.getAttributes(), "HOT");
        }

        @Override
        public void handleEvent(ColdEmissionEvent event) {
            processEmission(event.getLinkId(), event.getAttributes(), "COLD");
        }

        private void processEmission(Id<Link> linkId, Map<String, String> attributes, String condition) {
            linkEmissions.putIfAbsent(linkId, new HashMap<>());
            Map<String, Double> pollutantsForLink = linkEmissions.get(linkId);

            for (Map.Entry<String, String> entry : attributes.entrySet()) {
                String originalKey = entry.getKey();

                if (originalKey.equals("type") || originalKey.equals("time") ||
                        originalKey.equals("linkId") || originalKey.equals("vehicleId")) {
                    continue;
                }

                try {
                    double amount = Double.parseDouble(entry.getValue());
                    String granularKey = condition + "|" + originalKey;
                    pollutantsForLink.put(granularKey, pollutantsForLink.getOrDefault(granularKey, 0.0) + amount);
                } catch (NumberFormatException ignored) {
                }
            }
        }

        @Override
        public void reset(int iteration) {
            linkEmissions.clear();
        }

        public void writeToCsv(String filePath, Network network, String extractionMode) {
            try (BufferedWriter writer = new BufferedWriter(new FileWriter(filePath))) {

                Set<String> basePollutants = new HashSet<>();
                for (Map<String, Double> pollutants : linkEmissions.values()) {
                    for (String granularKey : pollutants.keySet()) {
                        String[] parts = granularKey.split("\\|");
                        if (parts.length == 2) {
                            basePollutants.add(parts[1]);
                        }
                    }
                }

                Set<String> sortedBasePollutants = new TreeSet<>(basePollutants);

                writer.write("LinkId,TrafficSituation");

                if (extractionMode.equals("TOTAL")) {
                    for (String pol : sortedBasePollutants) {
                        writer.write("," + pol);
                    }
                } else if (extractionMode.equals("HOT_COLD")) {
                    for (String pol : sortedBasePollutants) {
                        writer.write(",HOT_" + pol + ",COLD_" + pol);
                    }
                }
                writer.write("\n");

                for (Map.Entry<Id<Link>, Map<String, Double>> entry : linkEmissions.entrySet()) {
                    Id<Link> linkId = entry.getKey();
                    Link link = network.getLinks().get(linkId);

                    String trafficSituation = "Unknown";
                    if (link != null && link.getAttributes().getAttribute("hbefa_road_type") != null) {
                        trafficSituation = link.getAttributes().getAttribute("hbefa_road_type").toString();
                    }

                    writer.write(linkId.toString() + "," + trafficSituation);

                    Map<String, Double> granularData = entry.getValue();

                    for (String pol : sortedBasePollutants) {
                        double hotVal = granularData.getOrDefault("HOT|" + pol, 0.0);
                        double coldVal = granularData.getOrDefault("COLD|" + pol, 0.0);

                        if (extractionMode.equals("TOTAL")) {
                            double total = hotVal + coldVal;
                            writer.write("," + total);
                        } else if (extractionMode.equals("HOT_COLD")) {
                            writer.write("," + hotVal + "," + coldVal);
                        }
                    }
                    writer.write("\n");
                }
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
    }
}