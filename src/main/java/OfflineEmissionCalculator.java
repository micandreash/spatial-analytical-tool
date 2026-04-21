import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
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
import java.util.Map;

public class OfflineEmissionCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Emission Calculator...");

        // ==========================================
        // 1. DEFINE PATHS
        // ==========================================
        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/bavaria_1pct_network.xml/bavaria_1pct_network_3d.xml";
        String eventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output/ITERS/it.88/88.events.xml.gz";
        String vehiclesFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/simulation_output/output_vehicles.xml.gz";
        String hbefaHotFile = "D:/Michael_Thesis/data/hbefa/EFA_HOT_Vehcat_michael_thesis_weighted_v4_2.csv";
        String hbefaColdFile = "D:/Michael_Thesis/data/hbefa/EFA_ColdStart_Vehcat_michael_thesis_weighted_v4_2.csv";
        String outputFile = "D:/Michael_Thesis/data/indicators/emissions_per_link_with_gradient.csv";

        // ==========================================
        // 2. CONFIGURE MATSIM & EMISSIONS MODULE
        // ==========================================
        System.out.println("Setting up configurations...");
        Config config = ConfigUtils.createConfig();
        config.network().setInputFile(networkFile);
        config.vehicles().setVehiclesFile(vehiclesFile);

        // Inject the emissions configuration group (Adopted from Lion's approach)
        EmissionsConfigGroup emissionsConfig = new EmissionsConfigGroup();
        emissionsConfig.setAverageWarmEmissionFactorsFile(hbefaHotFile);
        emissionsConfig.setAverageColdEmissionFactorsFile(hbefaColdFile);

        // Use AverageSpeed method because we don't simulate detailed pedal-to-the-metal kinematics
        emissionsConfig.setEmissionsComputationMethod(EmissionsConfigGroup.EmissionsComputationMethod.AverageSpeed);
        emissionsConfig.setDetailedVsAverageLookupBehavior(EmissionsConfigGroup.DetailedVsAverageLookupBehavior.directlyTryAverageTable);
        emissionsConfig.setHbefaVehicleDescriptionSource(EmissionsConfigGroup.HbefaVehicleDescriptionSource.fromVehicleTypeDescription);
        emissionsConfig.setNonScenarioVehicles(EmissionsConfigGroup.NonScenarioVehicles.valueOf("ignore"));

        config.addModule(emissionsConfig);

        // ==========================================
        // 3. LOAD SCENARIO (Build the 3D network in RAM)
        // ==========================================
        System.out.println("Loading 3D Network into memory...");
        Scenario scenario = ScenarioUtils.loadScenario(config);

        System.out.println("Menerjemahkan tipe jalan OSM ke kategori HBEFA...");
        new org.matsim.contrib.emissions.VspHbefaRoadTypeMapping().addHbefaMappings(scenario.getNetwork());

        // ==========================================
        // 4. PREPARE THE EVENTS MANAGER & CUSTOM AGGREGATOR
        // ==========================================
        EventsManager eventsManager = EventsUtils.createEventsManager();

        // Instantiate the official MATSim Emission Module to do the heavy lifting (HBEFA math)
        new EmissionModule(scenario, eventsManager);

        // Create our custom Link-based aggregator to catch the mathematical results
        LinkEmissionAggregator aggregator = new LinkEmissionAggregator();
        eventsManager.addHandler(aggregator);

        // ==========================================
        // 5. RUN THE OFFLINE PLAYBACK
        // ==========================================
        System.out.println("Playing back events from last iteration. This might take a few minutes...");
        MatsimEventsReader reader = new MatsimEventsReader(eventsManager);
        reader.readFile(eventsFile);

        // ==========================================
        // 6. EXPORT TO CSV FOR PYTHON SPATIAL TOOL
        // ==========================================
        System.out.println("Exporting spatial emission data to CSV...");
        aggregator.writeToCsv(outputFile, scenario.getNetwork());
        System.out.println("DONE!");
    }

    // Custom Event Handler to catch emission events and aggregate them by Link ID
    private static class LinkEmissionAggregator implements WarmEmissionEventHandler, ColdEmissionEventHandler {

        // Data structure: Map<LinkId, Map<PollutantName, TotalAmount>>
        private final Map<Id<Link>, Map<String, Double>> linkEmissions = new HashMap<>();

        @Override
        public void handleEvent(WarmEmissionEvent event) {
            processEmission(event.getLinkId(), event.getAttributes());
        }

        @Override
        public void handleEvent(ColdEmissionEvent event) {
            processEmission(event.getLinkId(), event.getAttributes());
        }

        private void processEmission(Id<Link> linkId, Map<String, String> attributes) {
            // Ensure the link exists in our tracker
            linkEmissions.putIfAbsent(linkId, new HashMap<>());
            Map<String, Double> pollutantsForLink = linkEmissions.get(linkId);

            // Loop through all attributes in the event
            for (Map.Entry<String, String> entry : attributes.entrySet()) {
                String key = entry.getKey();

                // Skip non-pollutant metadata
                if (key.equals("type") || key.equals("time") || key.equals("linkId") || key.equals("vehicleId")) {
                    continue;
                }

                try {
                    double amount = Double.parseDouble(entry.getValue());
                    // Add the emission amount to the specific pollutant on this specific link
                    pollutantsForLink.put(key, pollutantsForLink.getOrDefault(key, 0.0) + amount);
                } catch (NumberFormatException e) {
                    // Ignore parsing errors for unexpected text attributes
                }
            }
        }

        @Override
        public void reset(int iteration) {
            linkEmissions.clear();
        }

        public void writeToCsv(String filePath, org.matsim.api.core.v01.network.Network network) {
            try (BufferedWriter writer = new BufferedWriter(new FileWriter(filePath))) {

                // Determine all unique pollutant types found during the simulation
                java.util.Set<String> allPollutants = new java.util.HashSet<>();
                for (Map<String, Double> pollutants : linkEmissions.values()) {
                    allPollutants.addAll(pollutants.keySet());
                }

                // Write Header
                writer.write("LinkId,TrafficSituation");
                for (String pollutant : allPollutants) {
                    writer.write("," + pollutant);
                }
                writer.write("\n");

                // Write Data
                for (Map.Entry<Id<Link>, Map<String, Double>> entry : linkEmissions.entrySet()) {
                    Id<Link> linkId = entry.getKey();

                    // Extract HBEFA road type (Traffic Situation)
                    org.matsim.api.core.v01.network.Link link = network.getLinks().get(linkId);
                    String trafficSituation = "Unknown";
                    if (link != null && link.getAttributes().getAttribute("hbefa_road_type") != null) {
                        trafficSituation = link.getAttributes().getAttribute("hbefa_road_type").toString();
                    }

                    // Write ID and Traffic Situation
                    writer.write(linkId.toString() + "," + trafficSituation);

                    // Write total emissions horizontally
                    for (String pollutant : allPollutants) {
                        double amount = entry.getValue().getOrDefault(pollutant, 0.0);
                        writer.write("," + amount);
                    }
                    writer.write("\n");
                }
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
    }
}